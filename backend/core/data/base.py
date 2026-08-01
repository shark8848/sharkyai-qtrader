"""DataSource abstract base class -- unified data protocol for all data providers."""

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class DataSource(ABC):
    """All data sources must implement this interface.

    Provides a unified protocol for fetching stock lists, daily kline data,
    realtime quotes, and financial data regardless of the underlying provider.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the data source."""
        ...

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for the data source (used in config/API)."""
        ...

    @abstractmethod
    async def get_stock_list(self) -> pd.DataFrame:
        """Fetch the list of all available stocks.

        Returns:
            DataFrame with columns: [symbol, name, market, industry]
        """
        ...

    @abstractmethod
    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Fetch daily OHLCV kline data for a single stock.

        Args:
            symbol: Stock code, e.g. "000001" or "SH600000".
            start_date: Start date in "YYYY-MM-DD" format.
            end_date: End date in "YYYY-MM-DD" format.
            adjust: Price adjustment mode: "qfq" (forward), "hfq" (backward), "" (none).

        Returns:
            DataFrame with columns: [date, open, high, low, close, volume, amount]
        """
        ...

    @abstractmethod
    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        """Fetch realtime quote snapshots for a list of stocks.

        Args:
            symbols: List of stock codes.

        Returns:
            DataFrame with columns: [symbol, name, price, change, change_pct,
                                     volume, amount, high, low, open, pre_close]
        """
        ...

    @abstractmethod
    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        """Fetch key financial indicators for a stock.

        Args:
            symbol: Stock code.

        Returns:
            DataFrame with financial data columns.
        """
        ...

    async def health_check(self) -> bool:
        """Check whether the data source is reachable. Override for custom logic."""
        return True
