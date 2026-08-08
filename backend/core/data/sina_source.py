"""Sina data source — direct connection to Sina Finance APIs.

Independent daily-kline channel using akshare's stock_zh_a_daily
(sina). Kept as a separate source so users can choose it explicitly and
it serves as a fallback when EastMoney / akshare aggregate is flaky.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import pandas as pd

from qtrader.backend.core.data.base import DataSource

logger = logging.getLogger(__name__)


class SinaSource(DataSource):
    """Data source backed by Sina Finance (新浪财经)."""

    @property
    def name(self) -> str:
        return "Sina"

    @property
    def source_id(self) -> str:
        return "sina"

    @property
    def capabilities(self) -> set[str]:
        return {"daily", "minute"}

    @property
    def data_format(self) -> str:
        return "api"

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def get_stock_list(self) -> pd.DataFrame:
        import akshare as ak

        try:
            df = await self._run_sync(ak.stock_info_a_code_name)
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
            logger.error(f"Sina get_stock_list failed: {e}")
            return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "hfq",
    ) -> pd.DataFrame:
        import akshare as ak

        try:
            # sina symbol: sh600519 / sz000001
            pure = symbol.lower()
            df = await self._run_sync(
                ak.stock_zh_a_daily,
                symbol=pure,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="hfq",
            )
            if df is None or df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
            df = df.reset_index() if "date" not in df.columns else df
            result = pd.DataFrame({
                "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
                "open": df["open"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "close": df["close"].astype(float),
                "volume": df["volume"].astype(float),
                "amount": df["amount"].astype(float) if "amount" in df.columns else 0.0,
            })
            return result
        except Exception as e:
            logger.error(f"Sina get_daily_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_minute_kline(
        self,
        symbol: str,
        date: str,
        period: str = "1",
    ) -> pd.DataFrame:
        import akshare as ak

        try:
            pure = symbol.lower()
            df = await self._run_sync(ak.stock_zh_a_minute, symbol=pure, period=period, adjust="qfq")
            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
            df["date"] = pd.to_datetime(df["day"]).dt.strftime("%Y-%m-%d %H:%M:%S")
            df = df[df["date"].str.startswith(date)]
            result = pd.DataFrame({
                "date": df["date"],
                "open": df["open"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "close": df["close"].astype(float),
                "volume": df["volume"].astype(float),
                "amount": df["amount"].astype(float) if "amount" in df.columns else 0.0,
            })
            return result
        except Exception as e:
            logger.error(f"Sina get_minute_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        logger.warning("Sina source does not provide realtime quotes")
        return pd.DataFrame(columns=[
            "symbol", "name", "price", "change", "change_pct",
            "volume", "amount", "high", "low", "open", "pre_close",
        ])

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        logger.warning("Sina source does not provide financial data")
        return pd.DataFrame()

    async def health_check(self) -> bool:
        try:
            import akshare as ak
            await self._run_sync(ak.stock_zh_a_daily, symbol="sh600519", start_date="20260101", end_date="20260201", adjust="hfq")
            return True
        except Exception:
            return False
