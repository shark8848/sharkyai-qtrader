"""Read local Qlib .bin data for charting.

Provides fast local-only access to daily OHLCV data stored in
Qlib's proprietary .bin format, without any network calls.
Also supports fetching unadjusted prices from akshare (cached).
"""

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

QLIB_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"
CALENDARS_DIR = QLIB_DATA_DIR / "calendars"
FEATURES_DIR = QLIB_DATA_DIR / "features"

FIELDS = ["open", "high", "low", "close", "volume", "amount"]

# Cache calendar in memory
_calendar_cache: list[str] | None = None


def _get_calendar() -> list[str]:
    """Load and cache the trading calendar."""
    global _calendar_cache
    if _calendar_cache is not None:
        return _calendar_cache
    cal_file = CALENDARS_DIR / "day.txt"
    if not cal_file.exists():
        return []
    _calendar_cache = [line.strip() for line in cal_file.read_text().splitlines() if line.strip()]
    return _calendar_cache


def read_local_kline(symbol: str, days: int = 120) -> pd.DataFrame:
    """Read daily OHLCV from local .bin files.

    Args:
        symbol: Stock symbol like 'sh600519' or 'SH600519'
        days: Number of recent trading days to return

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount
    """
    fname = symbol.lower()
    stock_dir = FEATURES_DIR / fname

    if not stock_dir.exists():
        return pd.DataFrame()

    calendar = _get_calendar()
    if not calendar:
        return pd.DataFrame()

    cal_len = len(calendar)
    result = {}

    for field in FIELDS:
        bin_file = stock_dir / f"{field}.day.bin"
        if not bin_file.exists():
            continue
        raw = np.fromfile(str(bin_file), dtype="<f")
        if len(raw) <= 1:
            continue
        start_idx = int(raw[0])
        values = raw[1:]
        result[field] = (start_idx, values)

    if "close" not in result:
        return pd.DataFrame()

    # Determine the valid range
    close_start, close_values = result["close"]
    data_len = len(close_values)

    # Calculate how many days to return
    actual_days = min(days, data_len)
    offset = data_len - actual_days

    # Build date index
    dates = []
    for i in range(offset, data_len):
        cal_idx = close_start + i
        if 0 <= cal_idx < cal_len:
            dates.append(calendar[cal_idx])
        else:
            dates.append("")

    # Build dataframe
    df_data = {"date": dates}
    for field in FIELDS:
        if field in result:
            start_idx, values = result[field]
            # Align with close data range
            field_offset = close_start + offset - start_idx
            field_end = field_offset + actual_days
            if field_offset >= 0 and field_end <= len(values):
                df_data[field] = values[field_offset:field_end].tolist()
            else:
                df_data[field] = [float("nan")] * actual_days
        else:
            df_data[field] = [float("nan")] * actual_days

    df = pd.DataFrame(df_data)
    # Filter out invalid dates
    df = df[df["date"] != ""].reset_index(drop=True)
    return df


def get_available_symbols() -> list[str]:
    """List all symbols that have local .bin data."""
    if not FEATURES_DIR.exists():
        return []
    symbols = []
    for d in sorted(FEATURES_DIR.iterdir()):
        if d.is_dir() and (d / "close.day.bin").exists():
            symbols.append(d.name)
    return symbols


# --- Unadjusted price fetch with cache ---
_raw_cache: dict[str, tuple[float, pd.DataFrame]] = {}  # symbol -> (timestamp, df)
_CACHE_TTL = 3600  # 1 hour


def read_raw_kline(symbol: str, days: int = 120) -> pd.DataFrame:
    """Fetch unadjusted daily kline from akshare (sina source) with cache.

    Args:
        symbol: e.g. 'sh600519' or 'sz000001'
        days: number of recent trading days to return

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount
    """
    import akshare as ak

    fname = symbol.lower()
    now = time.time()

    # Check cache
    if fname in _raw_cache:
        ts, cached_df = _raw_cache[fname]
        if now - ts < _CACHE_TTL and not cached_df.empty:
            return cached_df.tail(days).reset_index(drop=True)

    try:
        # Calculate date range (calendar days ≈ trading days * 1.6)
        end_dt = pd.Timestamp.now()
        start_dt = end_dt - pd.Timedelta(days=int(days * 1.6) + 10)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        df = ak.stock_zh_a_daily(
            symbol=fname, start_date=start_str, end_date=end_str, adjust=""
        )
        if df.empty:
            return pd.DataFrame()

        result = pd.DataFrame({
            "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
            "volume": df["volume"].astype(float),
            "amount": df.get("amount", pd.Series([0.0] * len(df))).astype(float),
        })
        _raw_cache[fname] = (now, result)
        return result.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.warning(f"Failed to fetch raw kline for {fname}: {e}")
        # Fallback: return cached even if expired
        if fname in _raw_cache:
            return _raw_cache[fname][1].tail(days).reset_index(drop=True)
        return pd.DataFrame()
