"""Qlib data source bridge.

Reads from qlib's local binary data (~/.qlib/qlib_data/cn_data) and
converts to the unified DataFrame format used by QTrader.
"""

import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from qtrader.backend.core.data.base import DataSource
from qtrader.backend.config import settings

logger = logging.getLogger(__name__)

# Qlib binary field mapping
_QLIB_FIELDS = {
    "open": "$open",
    "high": "$high",
    "low": "$low",
    "close": "$close",
    "volume": "$volume",
    "amount": "$amount",
}


class QlibSource(DataSource):
    """Data source that reads from qlib's local binary data store.

    This bridges qlib's proprietary binary format into QTrader's
    unified DataFrame interface, allowing qlib data to be used
    alongside other sources.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = data_dir or settings.qlib_data_dir

    @property
    def name(self) -> str:
        return "Qlib Local"

    @property
    def source_id(self) -> str:
        return "qlib"

    def _ensure_qlib_init(self):
        """Lazily initialize qlib if not already done."""
        import qlib
        from qlib.config import C
        if not C.registered:
            qlib.init(provider_uri=self._data_dir, region="cn")

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def get_stock_list(self) -> pd.DataFrame:
        try:
            instruments_path = Path(self._data_dir) / "instruments"
            if not instruments_path.exists():
                return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

            # Read all instruments from the 'all.txt' file
            all_file = instruments_path / "all.txt"
            if not all_file.exists():
                return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

            records = []
            with open(all_file, "r") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 1:
                        symbol = parts[0]
                        records.append({
                            "symbol": symbol,
                            "name": symbol,
                            "market": "SH" if symbol.startswith("SH") else "SZ",
                            "industry": "",
                        })
            return pd.DataFrame(records)
        except Exception as e:
            logger.error(f"Qlib get_stock_list failed: {e}")
            return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        try:
            from qlib.data import D
            self._ensure_qlib_init()

            def _fetch():
                fields = ["$open", "$high", "$low", "$close", "$volume", "$amount"]
                df = D.features(
                    [symbol],
                    fields,
                    start_time=start_date,
                    end_time=end_date,
                )
                return df

            df = await self._run_sync(_fetch)

            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

            # qlib returns MultiIndex (instrument, datetime)
            df = df.reset_index(level="datetime")
            result = pd.DataFrame({
                "date": df["datetime"].dt.strftime("%Y-%m-%d").values,
                "open": df["$open"].values,
                "high": df["$high"].values,
                "low": df["$low"].values,
                "close": df["$close"].values,
                "volume": df["$volume"].values,
                "amount": df["$amount"].values,
            })
            return result
        except Exception as e:
            logger.error(f"Qlib get_daily_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        # Qlib local data does not provide realtime quotes
        logger.warning("Qlib source does not support realtime quotes")
        return pd.DataFrame(columns=[
            "symbol", "name", "price", "change", "change_pct",
            "volume", "amount", "high", "low", "open", "pre_close",
        ])

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        # Qlib local data does not include financial statements directly
        logger.warning("Qlib source does not support financial data queries")
        return pd.DataFrame()

    async def health_check(self) -> bool:
        return Path(self._data_dir).exists()
