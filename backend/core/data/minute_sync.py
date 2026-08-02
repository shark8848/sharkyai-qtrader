"""Minute-level kline data synchronization engine.

Fetches 1-min (or other period) kline data from AKShare (sina source)
and stores as Parquet files organized by date for efficient querying.

Storage layout:
    ~/.qtrader/minute_data/
    ├── meta.json                  # sync metadata
    ├── 2026-07-31/
    │   ├── sh600519.parquet
    │   ├── sz000001.parquet
    │   └── ...
    └── 2026-07-30/
        └── ...
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .checkpoint import SyncCheckpoint

logger = logging.getLogger(__name__)

MINUTE_DATA_DIR = Path.home() / ".qtrader" / "minute_data"
META_FILE = MINUTE_DATA_DIR / "meta.json"

# Trading hours for A-share market (minutes from midnight)
TRADING_MINUTES = list(range(9 * 60 + 30, 11 * 60 + 31)) + list(range(13 * 60, 15 * 60 + 1))


class MinuteSyncTask:
    """Tracks progress of a minute-data sync operation."""

    def __init__(self):
        self.status = "idle"  # idle | running | done | error
        self.progress = 0.0
        self.message = ""
        self.total_stocks = 0
        self.done_stocks = 0
        self.success_stocks = 0
        self.skip_stocks = 0
        self.fail_stocks = 0
        self.dates_synced = 0
        self.base_synced = 0  # disk count at sync start
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self):
        overall_synced = self.base_synced + self.success_stocks
        full_total = max(self.total_stocks + self.skip_stocks, self.total_stocks, 1)
        overall_pct = round(overall_synced / full_total * 100, 1)
        return {
            "status": self.status,
            "progress": round(self.progress, 1),
            "message": self.message,
            "total_stocks": self.total_stocks,
            "done_stocks": self.done_stocks,
            "success_stocks": self.success_stocks,
            "skip_stocks": self.skip_stocks,
            "fail_stocks": self.fail_stocks,
            "overall_synced": overall_synced,
            "overall_pct": overall_pct,
            "dates_synced": self.dates_synced,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# Global sync task
_sync_task = MinuteSyncTask()
_sync_lock = threading.Lock()


def _count_disk_synced() -> int:
    """Count unique stocks that have parquet data on disk."""
    if not MINUTE_DATA_DIR.exists():
        return 0
    stocks = set()
    for date_dir in MINUTE_DATA_DIR.iterdir():
        if date_dir.is_dir() and date_dir.name[0].isdigit():
            for f in date_dir.glob("*.parquet"):
                stocks.add(f.stem)
    return len(stocks)


def get_minute_sync_status() -> dict:
    d = _sync_task.to_dict()
    # When not running, report actual disk state
    if _sync_task.status != "running":
        disk_count = _count_disk_synced()
        total = 5534
        d["overall_synced"] = disk_count
        d["overall_pct"] = round(disk_count / total * 100, 1) if total > 0 else 0
        d["total_stocks"] = total
    # Add data time range from date directories
    if MINUTE_DATA_DIR.exists():
        date_dirs = sorted(
            [p.name for p in MINUTE_DATA_DIR.iterdir()
             if p.is_dir() and p.name[0].isdigit()]
        )
        if date_dirs:
            d["data_start"] = date_dirs[0]
            d["data_end"] = date_dirs[-1]
            d["data_days"] = len(date_dirs)
    return d


def start_minute_sync(market: str = "all", period: str = "1") -> dict:
    """Start a background minute-data sync task."""
    global _sync_task
    with _sync_lock:
        if _sync_task.status == "running":
            return {"error": "分钟数据同步正在运行中，请等待完成"}
        _sync_task = MinuteSyncTask()
        _sync_task.status = "running"
        _sync_task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _sync_task.message = "正在初始化..."

    t = threading.Thread(target=_run_minute_sync, args=(market, period), daemon=True)
    t.start()
    return {"message": f"分钟数据同步已启动 (股票池: {market}, 周期: {period}分钟)"}


def _run_minute_sync(market: str, period: str):
    """Main sync logic for minute data."""
    global _sync_task
    try:
        _sync_task.message = "正在获取股票列表..."
        instruments = _load_instruments(market)
        if not instruments:
            raise ValueError(f"无法加载股票池 {market}")

        # Load metadata
        meta = _load_meta()

        # Pre-filter: scan disk directly to find latest date with data
        date_dirs = sorted(
            [d.name for d in MINUTE_DATA_DIR.iterdir()
             if d.is_dir() and d.name[0].isdigit()]
        ) if MINUTE_DATA_DIR.exists() else []

        if date_dirs:
            latest_date = date_dirs[-1]
            latest_dir = MINUTE_DATA_DIR / latest_date
            existing_files = {f.stem for f in latest_dir.glob("*.parquet")}
            pending = [s for s in instruments if s.lower() not in existing_files]
            logger.info(f"Minute pre-filter: latest={latest_date}, {len(existing_files)} stocks have data")
        else:
            pending = instruments

        already_done = len(instruments) - len(pending)

        # Load checkpoint — skip stocks completed before restart
        ckpt = SyncCheckpoint("minute")
        ckpt_completed = ckpt.load()
        if ckpt_completed:
            before = len(pending)
            pending = [s for s in pending if not ckpt.is_done(s)]
            resumed = before - len(pending)
            logger.info(f"Minute checkpoint resume: {resumed} done, {len(pending)} remaining")
        else:
            ckpt.start()

        _sync_task.total_stocks = len(pending)
        _sync_task.skip_stocks = len(instruments) - len(pending)
        _sync_task.base_synced = _count_disk_synced()
        logger.info(f"Minute pre-filter: {len(pending)} need sync, {len(instruments) - len(pending)} skipped")

        if not pending:
            ckpt.finish()
            _sync_task.status = "done"
            _sync_task.progress = 100
            _sync_task.message = f"所有 {len(instruments)} 只股票均已有最新分钟数据，无需同步"
            _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return

        _sync_task.message = f"需同步 {len(pending)} 只 (已跳过 {len(instruments) - len(pending)} 只)"

        # Fetch and store per-stock
        success_count = 0
        skip_count = 0
        fail_count = 0
        all_dates = set()

        for i, symbol in enumerate(pending):
            try:
                df = _fetch_minute_kline(symbol, period)
                if df is not None and not df.empty:
                    dates_written = _save_stock_parquet(symbol, df)
                    if dates_written:
                        all_dates.update(dates_written)
                        success_count += 1
                        ckpt.mark_done(symbol)
                    else:
                        skip_count += 1
                else:
                    skip_count += 1
            except Exception as e:
                fail_count += 1
                if fail_count <= 10:
                    logger.warning(f"Minute sync {symbol} failed: {e}")

            # Rate limit
            time.sleep(0.5)

            _sync_task.done_stocks = i + 1
            _sync_task.success_stocks = success_count
            _sync_task.skip_stocks = (len(instruments) - len(pending)) + skip_count
            _sync_task.fail_stocks = fail_count
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

        # Update metadata
        today = datetime.now().strftime("%Y-%m-%d")
        meta["last_sync_date"] = today
        meta["last_sync_period"] = period
        if all_dates:
            existing_dates = set(meta.get("available_dates", []))
            existing_dates.update(all_dates)
            meta["available_dates"] = sorted(existing_dates)
        _save_meta(meta)

        ckpt.finish()
        _sync_task.dates_synced = len(all_dates)
        _sync_task.status = "done"
        _sync_task.progress = 100
        _sync_task.message = (
            f"同步完成: {success_count} 只写入, {skip_count} 跳过, "
            f"{fail_count} 失败, 覆盖 {len(all_dates)} 个交易日"
        )
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Minute sync done: {success_count} stocks, {len(all_dates)} dates")

    except Exception as e:
        logger.exception("Minute sync failed")
        _sync_task.status = "error"
        _sync_task.error = str(e)
        _sync_task.message = f"同步失败: {e}"
        _sync_task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fetch_minute_kline(symbol: str, period: str, max_retries: int = 3) -> Optional[pd.DataFrame]:
    """Fetch minute kline from AKShare (sina source) with retry."""
    import akshare as ak

    sina_symbol = symbol.lower()  # SH600519 -> sh600519

    for attempt in range(max_retries):
        try:
            df = ak.stock_zh_a_minute(
                symbol=sina_symbol,
                period=period,
                adjust="hfq",
            )
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                time.sleep(wait)
            else:
                return None

    if df is None or df.empty:
        return None

    # Normalize columns: day, open, high, low, close, volume, amount
    df = df.copy()
    if "day" in df.columns:
        df["datetime"] = pd.to_datetime(df["day"])
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])
    else:
        df = df.reset_index()
        df["datetime"] = pd.to_datetime(df.iloc[:, 0])

    # Ensure numeric
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "amount" not in df.columns:
        df["amount"] = df["volume"] * df["close"]

    df["date"] = df["datetime"].dt.strftime("%Y-%m-%d")
    df["time"] = df["datetime"].dt.strftime("%H:%M:%S")

    return df


def _save_stock_parquet(symbol: str, df: pd.DataFrame) -> list[str]:
    """Save minute data as Parquet files, grouped by date.

    Returns list of dates that were written.
    """
    fname = symbol.lower()
    dates_written = []

    # Load meta to check which dates already have data for this stock
    meta = _load_meta()
    synced_stocks = meta.get("synced_stocks", {})

    for date_str, day_df in df.groupby("date"):
        # Check if this stock+date already exists
        day_dir = MINUTE_DATA_DIR / date_str
        parquet_path = day_dir / f"{fname}.parquet"

        if parquet_path.exists():
            # Append new data (avoid duplicates by datetime)
            try:
                existing = pd.read_parquet(parquet_path)
                combined = pd.concat([existing, day_df], ignore_index=True)
                combined = combined.drop_duplicates(subset=["datetime"], keep="last")
                combined = combined.sort_values("datetime").reset_index(drop=True)
                if len(combined) > len(existing):
                    day_dir.mkdir(parents=True, exist_ok=True)
                    combined.to_parquet(parquet_path, index=False, engine="pyarrow")
                    dates_written.append(date_str)
            except Exception:
                # If read fails, overwrite
                day_dir.mkdir(parents=True, exist_ok=True)
                day_df.sort_values("datetime").to_parquet(parquet_path, index=False, engine="pyarrow")
                dates_written.append(date_str)
        else:
            # New file
            day_dir.mkdir(parents=True, exist_ok=True)
            cols = ["datetime", "date", "time", "open", "high", "low", "close", "volume", "amount"]
            available_cols = [c for c in cols if c in day_df.columns]
            day_df[available_cols].sort_values("datetime").to_parquet(
                parquet_path, index=False, engine="pyarrow"
            )
            dates_written.append(date_str)

    return dates_written


def _load_instruments(market: str) -> list[str]:
    """Load instrument list (reuse daily sync logic)."""
    from qtrader.backend.core.data.qlib_sync import _load_instruments as load_daily
    return load_daily(market)


def _load_meta() -> dict:
    """Load sync metadata."""
    if META_FILE.exists():
        try:
            with open(META_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"available_dates": [], "synced_stocks": {}}


def _save_meta(meta: dict):
    """Save sync metadata."""
    MINUTE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(META_FILE, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# === Query functions (used by API) ===

def get_minute_data(symbol: str, date: str) -> Optional[pd.DataFrame]:
    """Query minute data for a stock on a specific date."""
    fname = symbol.lower()
    parquet_path = MINUTE_DATA_DIR / date / f"{fname}.parquet"
    if not parquet_path.exists():
        return None
    try:
        df = pd.read_parquet(parquet_path)
        return df
    except Exception as e:
        logger.error(f"Failed to read minute data {symbol} {date}: {e}")
        return None


def get_minute_calendar() -> list[str]:
    """Get list of dates that have minute data."""
    meta = _load_meta()
    dates = meta.get("available_dates", [])
    if dates:
        return dates
    # Fallback: scan directories
    if not MINUTE_DATA_DIR.exists():
        return []
    dates = []
    for d in MINUTE_DATA_DIR.iterdir():
        if d.is_dir() and d.name[0].isdigit():
            dates.append(d.name)
    return sorted(dates)


def get_minute_stocks_for_date(date: str) -> list[str]:
    """Get list of stocks that have minute data for a given date."""
    day_dir = MINUTE_DATA_DIR / date
    if not day_dir.exists():
        return []
    return [f.stem for f in day_dir.glob("*.parquet")]
