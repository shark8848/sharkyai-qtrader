"""StandardBar — unified data contract for all data sources.

Every source (akshare / eastmoney / sina / tushare / baostock / qlib_local)
produces StandardBar rows, and the Converter writes them into any target
storage (.bin / parquet / sqlite) in one consistent format.

This is the fix for the historical "amount missing → full re-sync forever"
bug: amount is a REQUIRED field here, never silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Valid frequency identifiers (qlib-style)
VALID_FREQS = {"1d", "1min", "5min", "15min", "30min", "60min"}
# Valid adjustment modes
VALID_ADJUST = {"none", "qfq", "hfq"}
# Required numeric fields (all must be finite and >= 0)
REQUIRED_FIELDS = ("open", "high", "low", "close", "volume", "amount")


@dataclass
class StandardBar:
    """One bar of market data in the unified schema."""

    symbol: str                 # "SH600519" (upper-case)
    datetime: str               # "YYYY-MM-DD" (daily) / "YYYY-MM-DD HH:MM:SS" (minute)
    freq: str                   # "1d" / "1min" / "5min" / "15min" / "30min" / "60min"
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float               # REQUIRED — missing values are flagged, never dropped
    adjusted: str = "hfq"       # "none" / "qfq" / "hfq"
    source_id: str = ""         # which channel produced this data
    vwap: Optional[float] = None
    paused: Optional[bool] = None

    def to_dict(self) -> dict:
        d = {
            "symbol": self.symbol,
            "datetime": self.datetime,
            "freq": self.freq,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "adjusted": self.adjusted,
            "source_id": self.source_id,
        }
        if self.vwap is not None:
            d["vwap"] = self.vwap
        if self.paused is not None:
            d["paused"] = self.paused
        return d


def validate_bars(bars: list[StandardBar]) -> list[StandardBar]:
    """Validate and clean a list of StandardBar.

    Rules:
      - all required numeric fields finite and >= 0 (amount included)
      - datetime strictly increasing (sorted + de-duped)
      - high >= open/close >= low (tolerate 1e-6 float noise)

    Returns the cleaned list (invalid bars dropped).
    """
    import math

    out: list[StandardBar] = []
    for b in bars:
        # freq / adjust sanity
        if b.freq not in VALID_FREQS:
            logger.warning(f"drop bar with invalid freq={b.freq}")
            continue
        if b.adjusted not in VALID_ADJUST:
            logger.warning(f"drop bar with invalid adjust={b.adjusted}")
            continue
        # numeric checks
        ok = True
        for f in REQUIRED_FIELDS:
            v = getattr(b, f)
            if v is None or not math.isfinite(v) or v < 0:
                ok = False
                break
        if not ok:
            logger.warning(f"drop bar {b.symbol} {b.datetime}: invalid numeric field")
            continue
        # OHLC consistency
        eps = 1e-6
        if not (b.high + eps >= b.open and b.high + eps >= b.close and b.low - eps <= b.open and b.low - eps <= b.close):
            logger.warning(f"drop bar {b.symbol} {b.datetime}: OHLC inconsistent")
            continue
        out.append(b)

    # sort by datetime, de-dupe
    out.sort(key=lambda b: b.datetime)
    seen: set[str] = set()
    unique: list[StandardBar] = []
    for b in out:
        key = (b.symbol, b.datetime)
        if key not in seen:
            seen.add(key)
            unique.append(b)
    return unique


def bars_from_dataframe(
    df,
    symbol: str,
    freq: str,
    adjusted: str = "hfq",
    source_id: str = "",
) -> list[StandardBar]:
    """Convert a unified DataFrame (date/open/high/low/close/volume/amount)
    into StandardBar rows. Used by sources that already return the standard
    column set. Missing 'amount' column yields amount=0.0 and a warning
    (kept, not dropped — the caller decides).
    """
    import pandas as pd

    if df is None or df.empty:
        return []

    # normalize date column name
    df = df.reset_index() if "date" not in df.columns else df
    if "date" not in df.columns:
        logger.warning(f"bars_from_dataframe: no 'date' column for {symbol}")
        return []

    # ensure numeric columns exist
    has_amount = "amount" in df.columns
    if not has_amount:
        logger.warning(f"bars_from_dataframe: {symbol} missing 'amount' column")

    bars = []
    for _, row in df.iterrows():
        date_val = row["date"]
        dt_str = (
            pd.to_datetime(date_val).strftime("%Y-%m-%d")
            if not isinstance(date_val, str)
            else date_val[:10]
        )
        try:
            amount = float(row["amount"]) if has_amount else 0.0
        except (TypeError, ValueError):
            amount = 0.0
        bars.append(
            StandardBar(
                symbol=symbol,
                datetime=dt_str,
                freq=freq,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                amount=amount,
                adjusted=adjusted,
                source_id=source_id,
            )
        )
    return validate_bars(bars)
