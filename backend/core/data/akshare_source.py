"""AKShare data source implementation.

Uses the akshare library to fetch A-share market data from
East Money, Sina Finance, and other public data providers.
"""

import asyncio
import logging
from functools import partial

import pandas as pd

from qtrader.backend.core.data.base import DataSource

logger = logging.getLogger(__name__)


class AKShareSource(DataSource):
    """Data source backed by AKShare (https://github.com/akfamily/akshare).

    Provides A-share daily kline, realtime quotes, stock list, and
    basic financial data through a unified interface.
    """

    @property
    def name(self) -> str:
        return "AKShare"

    @property
    def source_id(self) -> str:
        return "akshare"

    async def _run_sync(self, func, *args, **kwargs) -> pd.DataFrame:
        """Run a synchronous akshare call in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def get_stock_list(self) -> pd.DataFrame:
        import akshare as ak

        try:
            df = await self._run_sync(ak.stock_info_a_code_name)
            # columns: code, name
            result = pd.DataFrame({
                "symbol": df["code"].astype(str),
                "name": df["name"].astype(str),
                "market": df["code"].apply(
                    lambda x: "SH" if x.startswith("6") else "SZ"
                ),
                "industry": "",
            })
            return result
        except Exception as e:
            logger.error(f"AKShare get_stock_list failed: {e}")
            return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        import akshare as ak

        try:
            # akshare expects pure digits like "000001"
            pure_symbol = symbol.replace("SH", "").replace("SZ", "").replace(".", "")
            df = await self._run_sync(
                ak.stock_zh_a_hist,
                symbol=pure_symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust,
            )
            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

            result = pd.DataFrame({
                "date": pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d"),
                "open": df["开盘"].astype(float),
                "high": df["最高"].astype(float),
                "low": df["最低"].astype(float),
                "close": df["收盘"].astype(float),
                "volume": df["成交量"].astype(float),
                "amount": df["成交额"].astype(float),
            })
            return result
        except Exception as e:
            logger.error(f"AKShare get_daily_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        import akshare as ak

        try:
            df = await self._run_sync(ak.stock_zh_a_spot_em)
            # Filter to requested symbols
            pure_symbols = [s.replace("SH", "").replace("SZ", "").replace(".", "") for s in symbols]
            df = df[df["代码"].isin(pure_symbols)]

            result = pd.DataFrame({
                "symbol": df["代码"].astype(str).values,
                "name": df["名称"].astype(str).values,
                "price": df["最新价"].astype(float).values,
                "change": df["涨跌额"].astype(float).values,
                "change_pct": df["涨跌幅"].astype(float).values,
                "volume": df["成交量"].astype(float).values,
                "amount": df["成交额"].astype(float).values,
                "high": df["最高"].astype(float).values,
                "low": df["最低"].astype(float).values,
                "open": df["今开"].astype(float).values,
                "pre_close": df["昨收"].astype(float).values,
            })
            return result
        except Exception as e:
            logger.error(f"AKShare get_realtime_quote failed: {e}")
            return pd.DataFrame(columns=[
                "symbol", "name", "price", "change", "change_pct",
                "volume", "amount", "high", "low", "open", "pre_close",
            ])

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        import akshare as ak

        try:
            pure_symbol = symbol.replace("SH", "").replace("SZ", "").replace(".", "")
            df = await self._run_sync(
                ak.stock_financial_abstract_ths, symbol=pure_symbol
            )
            return df
        except Exception as e:
            logger.error(f"AKShare get_financial_data({symbol}) failed: {e}")
            return pd.DataFrame()

    async def health_check(self) -> bool:
        try:
            import akshare as ak
            # Quick lightweight call to verify connectivity
            await self._run_sync(ak.stock_info_a_code_name)
            return True
        except Exception:
            return False
