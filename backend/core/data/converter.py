"""Converter — write StandardBar into any target storage.

Unified ingestion path: any DataSource produces StandardBar, and Converter
writes it to qlib .bin / parquet / sqlite. All targets consume the SAME
schema, so field drift (e.g. the historical amount loss) cannot recur.

Bin format (qlib-compatible):
    [start_calendar_index, val0, val1, ...] as float32 little-endian.
    The calendar index maps each date to its position in the market calendar.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from qtrader.backend.core.data.schema import StandardBar

logger = logging.getLogger(__name__)

# qlib .bin fields (must match the qlib dump layout)
FIELDS = ["open", "high", "low", "close", "volume", "amount"]

# A-share market closes at 15:00; wait a buffer so the daily bar is final
MARKET_CLOSE_BUFFER = "15:30"


class Converter:
    """Converts StandardBar rows into storage formats."""

    def __init__(self, qlib_data_dir: Optional[str] = None, data_dir: Optional[str] = None):
        from qtrader.backend.config import settings

        self._qlib_data_dir = Path(qlib_data_dir or settings.qlib_data_dir)
        self._data_dir = Path(data_dir or settings.data_dir)

    # ------------------------------------------------------------------
    # qlib .bin
    # ------------------------------------------------------------------
    def to_qlib_bin(
        self,
        bars: list[StandardBar],
        calendar: list[str],
        freq: str = "1d",
        high_freq: bool = False,
    ) -> int:
        """Write bars into qlib .bin layout.

        Args:
            bars: StandardBar rows (all same symbol).
            calendar: full market calendar dates ["YYYY-MM-DD", ...] (index = position).
            freq: "1d" / "1min" / ... — determines subdir layout.
            high_freq: True → write under cn_data_1min layout (features/{symbol}).

        Returns: number of bars written.
        """
        if not bars:
            return 0
        symbol = bars[0].symbol
        cal_index = {d: i for i, d in enumerate(calendar)}

        # group by date -> {field: value}
        new_data: dict[str, dict[str, float]] = {}
        for b in bars:
            if b.datetime not in cal_index:
                logger.warning(f"to_qlib_bin: {symbol} date {b.datetime} not in calendar, skip")
                continue
            new_data[b.datetime] = {
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "amount": b.amount,
            }
        if not new_data:
            return 0

        fname = symbol.lower()
        base_dir = self._qlib_data_dir / ("cn_data_1min" if high_freq else "cn_data") / "features" / fname
        base_dir.mkdir(parents=True, exist_ok=True)

        for field in FIELDS:
            bin_path = base_dir / f"{field}.day.bin"

            # read existing bin
            existing_values: dict[str, float] = {}
            if bin_path.exists():
                raw = np.fromfile(str(bin_path), dtype="<f")
                if len(raw) > 1:
                    start_idx = int(raw[0])
                    values = raw[1:]
                    for j, val in enumerate(values):
                        idx = start_idx + j
                        if idx < len(calendar):
                            existing_values[calendar[idx]] = float(val)

            # merge new (overwrite existing dates)
            for date_str, field_vals in new_data.items():
                val = field_vals[field]
                if val is not None and not pd.isna(val):
                    existing_values[date_str] = float(val)
                elif date_str not in existing_values:
                    existing_values[date_str] = np.nan

            if not existing_values:
                continue

            sorted_dates = sorted(existing_values.keys())
            first_idx = cal_index[sorted_dates[0]]
            values = [existing_values[d] for d in sorted_dates]
            arr = np.hstack([[first_idx], values]).astype("<f")
            arr.tofile(str(bin_path))

        return len(new_data)

    # ------------------------------------------------------------------
    # Parquet
    # ------------------------------------------------------------------
    def to_parquet(self, bars: list[StandardBar], freq: str = "1d") -> Optional[Path]:
        """Write bars into parquet under ~/.qtrader/data/{freq}/.

        Returns the written file path, or None if empty.
        """
        if not bars:
            return None
        symbol = bars[0].symbol
        out_dir = self._data_dir / "data" / freq
        out_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([b.to_dict() for b in bars])
        path = out_dir / f"{symbol.lower()}.parquet"
        df.to_parquet(path, index=False)
        return path

    # ------------------------------------------------------------------
    # SQLite
    # ------------------------------------------------------------------
    def to_sqlite(self, bars: list[StandardBar]) -> int:
        """Write bars into the SQLite cache via data_store.

        Returns the number of rows written.
        """
        from qtrader.backend.core.data.store import data_store

        if not bars:
            return 0
        symbol = bars[0].symbol
        df = pd.DataFrame([b.to_dict() for b in bars])
        # rename datetime -> date for store compatibility
        df = df.rename(columns={"datetime": "date"})
        data_store.save_kline(df, symbol, source=bars[0].source_id or "unknown")
        return len(bars)


# Singleton
converter = Converter()
