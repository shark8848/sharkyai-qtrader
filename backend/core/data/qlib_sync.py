"""AKShare → Qlib .bin data synchronization engine.

Fetches daily kline data from AKShare and converts it to qlib's
proprietary binary format for use in model training and prediction.

Design: incremental per-stock writing — each stock is written to disk
immediately after fetch, so a restart never loses completed work.
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

from .checkpoint import SyncCheckpoint

logger = logging.getLogger(__name__)

QLIB_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"
CALENDARS_DIR = QLIB_DATA_DIR / "calendars"
FEATURES_DIR = QLIB_DATA_DIR / "features"
INSTRUMENTS_DIR = QLIB_DATA_DIR / "instruments"

# qlib .bin fields
FIELDS = ["open", "high", "low", "close", "volume", "amount"]


class QlibSyncTask:
    """Tracks progress of a sync operation."""

    def __init__(self):
        self.status = "idle"  # idle | running | done | error
        self.progress = 0.0
        self.message = ""
        self.total_stocks = 0
        self.done_stocks = 0
        self.success_stocks = 0
        self.skip_stocks = 0
        self.new_dates = 0
        self.base_synced = 0  # disk count at sync start
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self):
        # overall = disk baseline + newly synced in this run (capped at total)
        full_total = max(self.total_stocks + self.skip_stocks, self.total_stocks, 1)
        overall_synced = min(self.base_synced + self.success_stocks, full_total)
        overall_pct = round(overall_synced / full_total * 100, 1)
        fail_stocks = max(0, self.done_stocks - self.success_stocks - self.skip_stocks)
        return {
            "status": self.status,
            "progress": round(self.progress, 1),
            "message": self.message,
            "total_stocks": self.total_stocks,
            "done_stocks": self.done_stocks,
            "success_stocks": self.success_stocks,
            "skip_stocks": self.skip_stocks,
            "fail_stocks": fail_stocks,
            "overall_synced": overall_synced,
            "overall_pct": overall_pct,
            "new_dates": self.new_dates,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# Global sync task (only one at a time)
_sync_task = QlibSyncTask()
_sync_lock = threading.Lock()


def _count_disk_synced() -> int:
    """Count stocks that have .bin data on disk."""
    if not FEATURES_DIR.exists():
        return 0
    count = 0
    for d in FEATURES_DIR.iterdir():
        if d.is_dir() and (d / "close.day.bin").exists():
            count += 1
    return count


def get_sync_status() -> dict:
    d = _sync_task.to_dict()
    # When not running, report actual disk state
    if _sync_task.status != "running":
        disk_count = _count_disk_synced()
        total = 5534  # full A-share market
        d["overall_synced"] = disk_count
        d["overall_pct"] = round(disk_count / total * 100, 1) if total > 0 else 0
        d["total_stocks"] = total
    # Add data time range from calendar
    cal = _read_calendar()
    if cal:
        d["data_start"] = cal[0]
        d["data_end"] = cal[-1]
        d["data_days"] = len(cal)
    return d


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
    """Main sync logic (runs in background thread).

    Key design: each stock is written to disk immediately after fetch.
    Calendar is updated first so bin indices are stable.
    On restart, already-synced stocks are automatically skipped.
    """
    global _sync_task
    try:
        _sync_task.message = "正在获取股票列表..."
        instruments = _load_instruments(market)
        if not instruments:
            raise ValueError(f"无法加载股票池 {market}")

        # Read existing calendar
        existing_cal = _read_calendar()
        fetch_end = datetime.now().strftime("%Y%m%d")
        full_start = existing_cal[0].replace("-", "") if existing_cal else "19991110"

        # Step 1: Discover new trading dates by fetching a liquid stock (贵州茅台)
        _sync_task.message = "正在获取最新交易日历..."
        new_cal = _update_calendar(existing_cal, full_start, fetch_end)
        _sync_task.new_dates = len(new_cal) - len(existing_cal)
        cal_index = {d: i for i, d in enumerate(new_cal)}
        logger.info(f"Calendar: {len(existing_cal)} -> {len(new_cal)} days (+{_sync_task.new_dates})")

        # Step 2: Pre-filter — only keep stocks that actually need syncing
        _sync_task.message = "正在检查哪些股票需要同步..."
        pending = [s for s in instruments if not _stock_is_current(s, len(new_cal))]
        already_done = len(instruments) - len(pending)
        logger.info(f"Pre-filter: {len(pending)} need sync, {already_done} already current")

        # Step 2b: Load checkpoint — skip stocks completed before restart
        ckpt = SyncCheckpoint("daily")
        ckpt_completed = ckpt.load()
        if ckpt_completed:
            before = len(pending)
            pending = [s for s in pending if not ckpt.is_done(s)]
            resumed = before - len(pending)
            logger.info(f"Checkpoint resume: {resumed} stocks already done, {len(pending)} remaining")
        else:
            ckpt.start()

        _sync_task.total_stocks = len(pending)
        _sync_task.skip_stocks = len(instruments) - len(pending)
        _sync_task.base_synced = _count_disk_synced()

        if not pending:
            ckpt.finish()
            _sync_task.status = "done"
            _sync_task.progress = 100
            _sync_task.message = f"所有 {len(instruments)} 只股票均已是最新，无需同步"
            _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return

        _sync_task.message = f"需同步 {len(pending)} 只 (已跳过 {len(instruments) - len(pending)} 只)"

        # Step 3: Process only pending stocks — fetch and write immediately
        last_cal_date = new_cal[-1] if new_cal else ""
        success_count = 0
        fail_count = 0

        for i, symbol in enumerate(pending):
            try:
                df = _fetch_stock_kline(symbol, full_start, fetch_end)
                if df is not None and not df.empty:
                    _write_stock_bins(symbol, df, cal_index)
                    success_count += 1
                    _sync_task.success_stocks = success_count
                    ckpt.mark_done(symbol)
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                if fail_count <= 10:
                    logger.warning(f"Sync {symbol} failed: {e}")

            # Rate limit (only for actual network calls)
            time.sleep(0.5)

            _sync_task.done_stocks = i + 1
            _sync_task.progress = (i + 1) / len(pending) * 100
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - datetime.strptime(
                    _sync_task.started_at, "%Y-%m-%d %H:%M:%S")).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 1
                remaining = (len(pending) - i - 1) / rate / 60
                _sync_task.message = (
                    f"已处理 {i+1}/{len(pending)} "
                    f"({success_count} 成功, {fail_count} 失败) "
                    f"预计剩余 {remaining:.0f} 分钟"
                )

        # Step 4: Update instruments file
        _update_instruments(instruments, new_cal)

        total_skipped = len(instruments) - len(pending)
        ckpt.finish()
        _sync_task.status = "done"
        _sync_task.progress = 100
        _sync_task.message = (
            f"同步完成: {success_count} 只写入, {total_skipped} 只已是最新, "
            f"{fail_count} 只失败, 日历至 {last_cal_date}"
        )
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Qlib sync done: {success_count} written, {total_skipped} skipped, {fail_count} failed")

    except Exception as e:
        logger.exception("Qlib sync failed")
        _sync_task.status = "error"
        _sync_task.error = str(e)
        _sync_task.message = f"同步失败: {e}"
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stock_is_current(symbol: str, cal_len: int) -> bool:
    """Check if a stock's .bin data already covers recent calendar dates."""
    fname = symbol.lower()
    close_bin = FEATURES_DIR / fname / "close.day.bin"
    if not close_bin.exists():
        return False
    try:
        raw = np.fromfile(str(close_bin), dtype="<f")
        if len(raw) <= 1:
            return False
        data_len = len(raw) - 1
        start_idx = int(raw[0])
        # If data reaches within 5 days of calendar end, consider it current
        return (start_idx + data_len) >= (cal_len - 5)
    except Exception:
        return False


def _update_calendar(existing_cal: list[str], start: str, end: str) -> list[str]:
    """Fetch trading calendar from a liquid stock and merge with existing."""
    import akshare as ak

    new_dates = set()
    # Use 贵州茅台 (sh600519) as calendar reference — most liquid, never suspended
    try:
        df = ak.stock_zh_a_daily(symbol="sh600519", start_date=start, end_date=end, adjust="hfq")
        if df is not None and not df.empty:
            df = df.reset_index() if "date" not in df.columns else df
            dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist()
            new_dates.update(dates)
    except Exception as e:
        logger.warning(f"Calendar fetch from sh600519 failed: {e}")
        # Try 平安银行 as fallback
        try:
            df = ak.stock_zh_a_daily(symbol="sz000001", start_date=start, end_date=end, adjust="hfq")
            if df is not None and not df.empty:
                df = df.reset_index() if "date" not in df.columns else df
                dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist()
                new_dates.update(dates)
        except Exception:
            pass

    if not new_dates:
        return existing_cal

    # Merge and save
    all_dates = sorted(set(existing_cal) | new_dates)
    CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
    cal_file = CALENDARS_DIR / "day.txt"
    with open(cal_file, "w") as f:
        for d in all_dates:
            f.write(d + "\n")
    logger.info(f"Calendar updated: {len(all_dates)} days ({all_dates[0]} ~ {all_dates[-1]})")
    return all_dates


def _write_stock_bins(symbol: str, df: pd.DataFrame, cal_index: dict):
    """Write .bin files for a single stock immediately to disk.

    Merges new data with existing .bin content.
    """
    fname = symbol.lower()
    feat_dir = FEATURES_DIR / fname
    feat_dir.mkdir(parents=True, exist_ok=True)

    # Build a date->row lookup for new data
    new_data = {}
    for _, row in df.iterrows():
        date_str = row["date"]
        if date_str in cal_index:
            new_data[date_str] = row

    if not new_data:
        return

    calendar = sorted(cal_index.keys())

    for field in FIELDS:
        if field not in df.columns:
            continue
        bin_path = feat_dir / f"{field}.day.bin"

        # Read existing bin data
        existing_values = {}
        if bin_path.exists():
            raw = np.fromfile(str(bin_path), dtype="<f")
            if len(raw) > 1:
                start_idx = int(raw[0])
                values = raw[1:]
                for j, val in enumerate(values):
                    idx = start_idx + j
                    if idx < len(calendar):
                        existing_values[calendar[idx]] = val

        # Merge new data (overwrite existing with new)
        for date_str, row in new_data.items():
            val = row.get(field)
            if val is not None and not pd.isna(val):
                existing_values[date_str] = float(val)
            elif date_str not in existing_values:
                existing_values[date_str] = np.nan

        if not existing_values:
            continue

        # Write bin: [start_calendar_index, val0, val1, ...]
        sorted_dates = sorted(existing_values.keys())
        first_idx = cal_index[sorted_dates[0]]
        values = [existing_values[d] for d in sorted_dates]
        arr = np.hstack([[first_idx], values]).astype("<f")
        arr.tofile(str(bin_path))


def _load_instruments(market: str) -> list[str]:
    """Load instrument list.

    When market='all', fetch full A-share list from AKShare (5000+ stocks).
    Otherwise read from qlib instruments file (csi300, csi500, etc.).
    """
    if market == "all":
        return _fetch_all_stock_symbols()

    inst_file = INSTRUMENTS_DIR / f"{market}.txt"
    if not inst_file.exists():
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

    # stock_zh_a_daily returns: date, open, high, low, close, volume, amount
    df = df.reset_index() if "date" not in df.columns else df
    needed = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in needed if c in df.columns]
    df = df[available].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    if "amount" not in df.columns:
        df["amount"] = df["volume"] * df["close"]

    return df


def _update_instruments(instruments: list[str], calendar: list[str]):
    """Update instruments file with extended end dates."""
    if not calendar:
        return
    end_date = calendar[-1]
    start_date = calendar[0]

    INSTRUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    all_file = INSTRUMENTS_DIR / "all.txt"
    with open(all_file, "w") as f:
        for sym in instruments:
            f.write(f"{sym}\t{start_date}\t{end_date}\n")
