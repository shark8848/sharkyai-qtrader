"""AKShare → Qlib .bin data synchronization engine.

Fetches daily kline data from AKShare and converts it to qlib's
proprietary binary format for use in model training and prediction.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

QLIB_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"
CALENDARS_DIR = QLIB_DATA_DIR / "calendars"
FEATURES_DIR = QLIB_DATA_DIR / "features"
INSTRUMENTS_DIR = QLIB_DATA_DIR / "instruments"

# qlib .bin fields mapped from AKShare kline columns
FIELD_MAP = {
    "open": "$open",
    "high": "$high",
    "low": "$low",
    "close": "$close",
    "volume": "$volume",
    "amount": "$amount",
}


class QlibSyncTask:
    """Tracks progress of a sync operation."""

    def __init__(self):
        self.status = "idle"  # idle | running | done | error
        self.progress = 0.0
        self.message = ""
        self.total_stocks = 0
        self.done_stocks = 0
        self.new_dates = 0
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status,
            "progress": round(self.progress, 1),
            "message": self.message,
            "total_stocks": self.total_stocks,
            "done_stocks": self.done_stocks,
            "new_dates": self.new_dates,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# Global sync task (only one at a time)
_sync_task = QlibSyncTask()
_sync_lock = threading.Lock()


def get_sync_status() -> dict:
    return _sync_task.to_dict()


def start_sync(market: str = "all") -> dict:
    """Start a background sync task."""
    global _sync_task
    with _sync_lock:
        if _sync_task.status == "running":
            return {"error": "同步任务正在运行中，请等待完成"}
        _sync_task = QlibSyncTask()
        _sync_task.status = "running"
        _sync_task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _sync_task.message = "正在初始化..."

    t = threading.Thread(target=_run_sync, args=(market,), daemon=True)
    t.start()
    return {"message": f"同步任务已启动 (股票池: {market})"}


def _run_sync(market: str):
    """Main sync logic (runs in background thread)."""
    global _sync_task
    try:
        _sync_task.message = "正在获取股票列表..."
        instruments = _load_instruments(market)
        if not instruments:
            raise ValueError(f"无法加载股票池 {market}")

        _sync_task.total_stocks = len(instruments)
        _sync_task.message = f"共 {len(instruments)} 只股票待同步"

        # Read existing calendar
        existing_cal = _read_calendar()
        last_date = existing_cal[-1] if existing_cal else "1999-01-01"
        first_date = existing_cal[0] if existing_cal else "1999-01-01"
        fetch_end = datetime.now().strftime("%Y%m%d")
        # 对已有近期数据的股票做增量同步；对其余股票从日历起始日全量拉取
        incremental_start = (pd.Timestamp(last_date) + timedelta(days=1)).strftime("%Y%m%d")
        full_start = first_date.replace("-", "")

        _sync_task.message = f"同步中 (增量: {incremental_start}起, 全量: {full_start}起)"
        logger.info(f"Qlib sync: incremental={incremental_start}, full={full_start}, {len(instruments)} stocks")

        # Fetch data and collect new calendar dates
        all_new_dates = set()
        success_count = 0
        fail_count = 0

        for i, symbol in enumerate(instruments):
            # 判断该股票的 .bin 数据是否已覆盖近期（检查 close.day.bin 的数据量）
            fname = symbol.lower()
            feat_dir = FEATURES_DIR / fname
            close_bin = feat_dir / "close.day.bin"
            has_recent_data = False
            if close_bin.exists():
                raw = np.fromfile(str(close_bin), dtype="<f")
                if len(raw) > 1:
                    # 第一个元素是 calendar 起始索引，剩余是数据值
                    data_len = len(raw) - 1
                    start_idx = int(raw[0])
                    # 如果数据覆盖到日历末尾附近，认为已是最新
                    if start_idx + data_len >= len(existing_cal) - 5:
                        has_recent_data = True
            fetch_start = incremental_start if has_recent_data else full_start

            try:
                df = _fetch_stock_kline(symbol, fetch_start, fetch_end)
                if df is not None and not df.empty:
                    dates = df["date"].tolist()
                    all_new_dates.update(dates)
                    # Store for later bin writing
                    _write_stock_bin(symbol, df, existing_cal, all_new_dates)
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                if fail_count <= 5:
                    logger.warning(f"Sync {symbol} failed: {e}")

            # 请求间隔，避免被数据源限流
            time.sleep(0.5)

            _sync_task.done_stocks = i + 1
            _sync_task.progress = (i + 1) / len(instruments) * 90  # reserve 10% for finalization
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - datetime.strptime(_sync_task.started_at, "%Y-%m-%d %H:%M:%S")).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 1
                remaining = (len(instruments) - i - 1) / rate / 60
                _sync_task.message = (
                    f"已同步 {i+1}/{len(instruments)} "
                    f"({success_count} 成功, {fail_count} 跳过) "
                    f"预计剩余 {remaining:.0f} 分钟"
                )

        # Finalize: update calendar and rewrite bins with proper calendar alignment
        _sync_task.message = "正在更新交易日历和索引..."
        _sync_task.progress = 92
        new_cal = _finalize_calendar(existing_cal, all_new_dates)
        _sync_task.new_dates = len(new_cal) - len(existing_cal)

        # Rewrite all bins with updated calendar (needed for correct index offset)
        _sync_task.message = "正在重写数据索引..."
        _sync_task.progress = 95
        _rewrite_all_bins(new_cal, instruments, fetch_start, fetch_end)

        # Update instruments file
        _sync_task.progress = 98
        _update_instruments(instruments, new_cal)

        _sync_task.status = "done"
        _sync_task.progress = 100
        _sync_task.message = (
            f"同步完成: {success_count} 只股票, "
            f"新增 {_sync_task.new_dates} 个交易日, "
            f"日历延伸至 {new_cal[-1] if new_cal else 'N/A'}"
        )
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Qlib sync done: {success_count} stocks, {len(new_cal)} calendar days")

    except Exception as e:
        logger.exception("Qlib sync failed")
        _sync_task.status = "error"
        _sync_task.error = str(e)
        _sync_task.message = f"同步失败: {e}"
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_instruments(market: str) -> list[str]:
    """Load instrument list.

    When market='all', fetch full A-share list from AKShare (5000+ stocks).
    Otherwise read from qlib instruments file (csi300, csi500, etc.).
    """
    if market == "all":
        return _fetch_all_stock_symbols()

    inst_file = INSTRUMENTS_DIR / f"{market}.txt"
    if not inst_file.exists():
        # Fallback to full market
        return _fetch_all_stock_symbols()
    symbols = []
    with open(inst_file) as f:
        for line in f:
            parts = line.strip().split("\t")
            if parts:
                symbols.append(parts[0])
    return symbols


def _fetch_all_stock_symbols() -> list[str]:
    """Fetch all A-share stock symbols from AKShare and convert to qlib format."""
    import akshare as ak

    try:
        df = ak.stock_info_a_code_name()
        # df columns: code, name
        symbols = []
        for code in df["code"].astype(str):
            code = code.strip()
            if code.startswith("6"):
                symbols.append(f"SH{code}")
            elif code.startswith(("0", "3")):
                symbols.append(f"SZ{code}")
            elif code.startswith(("4", "8")):
                symbols.append(f"BJ{code}")
            else:
                symbols.append(f"SZ{code}")
        logger.info(f"Fetched {len(symbols)} stocks from AKShare")
        return symbols
    except Exception as e:
        logger.error(f"Failed to fetch stock list from AKShare: {e}")
        # Fallback to local all.txt
        all_file = INSTRUMENTS_DIR / "all.txt"
        if all_file.exists():
            with open(all_file) as f:
                return [line.strip().split("\t")[0] for line in f if line.strip()]
        return []


def _read_calendar() -> list[str]:
    """Read existing calendar dates."""
    cal_file = CALENDARS_DIR / "day.txt"
    if not cal_file.exists():
        return []
    with open(cal_file) as f:
        return [line.strip() for line in f if line.strip()]


def _fetch_stock_kline(symbol: str, start: str, end: str, max_retries: int = 3) -> Optional[pd.DataFrame]:
    """Fetch daily kline from AKShare (sina source) for a single stock with retry."""
    import akshare as ak

    # Convert qlib symbol (SH600519) to sina format (sh600519)
    sina_symbol = symbol.lower()

    for attempt in range(max_retries):
        try:
            df = ak.stock_zh_a_daily(
                symbol=sina_symbol,
                start_date=start,
                end_date=end,
                adjust="hfq",
            )
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2  # 2s, 4s, 6s backoff
                time.sleep(wait)
            else:
                return None

    if df is None or df.empty:
        return None

    # stock_zh_a_daily returns English columns: date, open, high, low, close, volume, amount
    df = df.reset_index() if "date" not in df.columns else df
    needed = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in needed if c in df.columns]
    df = df[available].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    if "amount" not in df.columns:
        df["amount"] = df["volume"] * df["close"]

    return df


def _write_stock_bin(symbol: str, df: pd.DataFrame, calendar: list[str], all_dates: set):
    """Temporary storage during sync - actual bin writing happens in finalize."""
    # Store fetched data in memory for the finalize step
    if not hasattr(_run_sync, "_stock_data"):
        _run_sync._stock_data = {}
    _run_sync._stock_data[symbol] = df


def _finalize_calendar(existing: list[str], new_dates: set) -> list[str]:
    """Merge new dates into calendar and save."""
    all_dates = sorted(set(existing) | new_dates)
    CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
    cal_file = CALENDARS_DIR / "day.txt"
    with open(cal_file, "w") as f:
        for d in all_dates:
            f.write(d + "\n")
    return all_dates


def _rewrite_all_bins(calendar: list[str], instruments: list[str], fetch_start: str, fetch_end: str):
    """Rewrite .bin files for stocks that have new data."""
    stock_data = getattr(_run_sync, "_stock_data", {})
    if not stock_data:
        return

    cal_index = {d: i for i, d in enumerate(calendar)}
    fields = ["open", "high", "low", "close", "volume", "amount"]

    for symbol, df in stock_data.items():
        # Convert symbol to qlib fname format (sh600519)
        fname = symbol.lower()
        feat_dir = FEATURES_DIR / fname
        feat_dir.mkdir(parents=True, exist_ok=True)

        for field in fields:
            if field not in df.columns:
                continue
            bin_path = feat_dir / f"{field}.day.bin"

            # Read existing bin data if present
            existing_data = {}
            if bin_path.exists():
                raw = np.fromfile(str(bin_path), dtype="<f")
                if len(raw) > 1:
                    start_idx = int(raw[0])
                    values = raw[1:]
                    for j, val in enumerate(values):
                        idx = start_idx + j
                        if idx < len(calendar):
                            existing_data[calendar[idx]] = val

            # Merge new data
            for _, row in df.iterrows():
                date_str = row["date"]
                if date_str in cal_index:
                    existing_data[date_str] = float(row[field]) if not pd.isna(row[field]) else np.nan

            if not existing_data:
                continue

            # Write bin: [start_index, val0, val1, ...]
            sorted_dates = sorted(existing_data.keys())
            first_idx = cal_index[sorted_dates[0]]
            values = [existing_data[d] for d in sorted_dates]
            arr = np.hstack([[first_idx], values]).astype("<f")
            arr.tofile(str(bin_path))

    # Clear stored data
    _run_sync._stock_data = {}


def _update_instruments(instruments: list[str], calendar: list[str]):
    """Update instruments file with extended end dates."""
    if not calendar:
        return
    end_date = calendar[-1]
    start_date = calendar[0]

    INSTRUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    # Update all.txt
    all_file = INSTRUMENTS_DIR / "all.txt"
    with open(all_file, "w") as f:
        for sym in instruments:
            f.write(f"{sym}\t{start_date}\t{end_date}\n")
