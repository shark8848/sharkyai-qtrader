"""Data source manager -- registry, switching, and caching layer."""

import logging
from typing import Optional

import pandas as pd

from qtrader.backend.core.data.base import DataSource
from qtrader.backend.core.data.store import data_store

logger = logging.getLogger(__name__)


class DataManager:
    """Central manager for data sources.

    Responsibilities:
    - Register and list available data sources
    - Switch active data source at runtime
    - Transparent caching: serve from SQLite when possible, fetch on miss
    - Incremental kline updates
    """

    def __init__(self):
        self._sources: dict[str, DataSource] = {}
        self._active_source_id: str = ""

    async def initialize(self):
        """Register built-in data sources on startup."""
        from qtrader.backend.core.data.akshare_source import AKShareSource
        from qtrader.backend.core.data.qlib_source import QlibSource
        from qtrader.backend.config import settings

        akshare = AKShareSource()
        qlib = QlibSource()
        self.register(akshare)
        self.register(qlib)

        # Set default active source
        if settings.default_data_source in self._sources:
            self._active_source_id = settings.default_data_source
        elif self._sources:
            self._active_source_id = next(iter(self._sources))
        logger.info(f"DataManager initialized. Active source: {self._active_source_id}")

    async def shutdown(self):
        """Cleanup on application shutdown."""
        logger.info("DataManager shutdown")

    def register(self, source: DataSource):
        """Register a new data source."""
        self._sources[source.source_id] = source
        logger.info(f"Registered data source: {source.source_id} ({source.name})")

    def list_sources(self) -> list[dict]:
        """List all registered data sources."""
        result = []
        for sid, src in self._sources.items():
            result.append({
                "id": sid,
                "name": src.name,
                "active": sid == self._active_source_id,
            })
        return result

    def switch_source(self, source_id: str) -> bool:
        """Switch the active data source."""
        if source_id not in self._sources:
            return False
        self._active_source_id = source_id
        logger.info(f"Switched active data source to: {source_id}")
        return True

    @property
    def active_source(self) -> DataSource:
        """Get the currently active data source."""
        return self._sources[self._active_source_id]

    async def get_stock_list(self, use_cache: bool = True) -> pd.DataFrame:
        """Get stock list, preferring cache."""
        src = self.active_source
        if use_cache:
            cached = data_store.load_stock_list(src.source_id)
            if not cached.empty:
                return cached
        df = await src.get_stock_list()
        data_store.save_stock_list(df, src.source_id)
        return df

    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get daily kline data with incremental caching.

        Strategy:
        1. Check what's already cached
        2. Fetch only the missing date range from the source
        3. Merge cached + new data
        """
        src = self.active_source

        if use_cache:
            cached = data_store.load_kline(symbol, start_date, end_date, src.source_id)
            if not cached.empty:
                latest_cached = cached["date"].max()
                if latest_cached >= end_date:
                    return cached
                # Incremental: fetch only from latest_cached+1 to end_date
                fetch_start = pd.Timestamp(latest_cached) + pd.Timedelta(days=1)
                fetch_start_str = fetch_start.strftime("%Y-%m-%d")
            else:
                fetch_start_str = start_date
        else:
            fetch_start_str = start_date

        # Fetch missing data from source
        new_data = await src.get_daily_kline(symbol, fetch_start_str, end_date, adjust)
        if not new_data.empty:
            data_store.save_kline(new_data, symbol, src.source_id)

        # Return merged result from cache
        return data_store.load_kline(symbol, start_date, end_date, src.source_id)

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        """Get realtime quotes (no caching for realtime data)."""
        return await self.active_source.get_realtime_quote(symbols)

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        """Get financial data."""
        return await self.active_source.get_financial_data(symbol)

    async def sync_kline(self, symbol: str, start_date: str, end_date: str) -> dict:
        """Force re-sync kline data (bypass cache)."""
        src = self.active_source
        df = await src.get_daily_kline(symbol, start_date, end_date)
        data_store.save_kline(df, symbol, src.source_id)
        return {"symbol": symbol, "rows": len(df), "source": src.source_id}


# Singleton
data_manager = DataManager()
