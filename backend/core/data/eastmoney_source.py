"""EastMoney data source — direct connection to 东方财富 APIs.

Preferred channel for A-share daily klines and realtime quotes. Daily
history and realtime come straight from EastMoney push2his/push2, which is
stable; minute klines can be flaky (RemoteDisconnected), so we fall back
to the Sina channel via akshare's stock_zh_a_minute when that happens.

Same vendor as the trading-layer EastMoneyBroker for consistency.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import pandas as pd

from qtrader.backend.core.data.base import DataSource
from qtrader.backend.core.data.schema import bars_from_dataframe

logger = logging.getLogger(__name__)


class EastMoneySource(DataSource):
    """Data source backed by EastMoney (东方财富)."""

    @property
    def name(self) -> str:
        return "东方财富"

    @property
    def source_id(self) -> str:
        return "eastmoney"

    @property
    def capabilities(self) -> set[str]:
        return {"daily", "minute", "realtime", "stock_list", "financial"}

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
            logger.error(f"EastMoney get_stock_list failed: {e}")
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
            pure_symbol = symbol.replace("SH", "").replace("SZ", "").replace(".", "")
            df = await self._run_sync(
                ak.stock_zh_a_hist,
                symbol=pure_symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust,
                timeout=30,  # EastMoney supports explicit timeout
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
            logger.error(f"EastMoney get_daily_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_minute_kline(
        self,
        symbol: str,
        date: str,
        period: str = "1",
    ) -> pd.DataFrame:
        """EastMoney minute kline with Sina fallback.

        EastMoney's stock_zh_a_hist_min_em occasionally drops the
        connection; on failure we fall back to akshare's sina-based
        stock_zh_a_minute so the sync never hard-fails.
        """
        import akshare as ak

        pure_symbol = symbol.replace("SH", "").replace("SZ", "").replace(".", "")
        # 1) try EastMoney
        try:
            df = await self._run_sync(
                ak.stock_zh_a_hist_min_em,
                symbol=pure_symbol,
                period=period,
                start_date=f"{date} 09:30:00",
                end_date=f"{date} 15:00:00",
                adjust="",
            )
            if not df.empty:
                # EM returns columns: 时间/开盘/收盘/最高/最低/成交量/成交额...
                result = pd.DataFrame({
                    "date": pd.to_datetime(df["时间"]).dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": df["开盘"].astype(float),
                    "high": df["最高"].astype(float),
                    "low": df["最低"].astype(float),
                    "close": df["收盘"].astype(float),
                    "volume": df["成交量"].astype(float),
                    "amount": df["成交额"].astype(float),
                })
                return result
        except Exception as e:
            logger.warning(f"EastMoney minute({symbol}) failed, fallback to Sina: {e}")

        # 2) Sina fallback
        try:
            df = await self._run_sync(
                ak.stock_zh_a_minute,
                symbol=pure_symbol,
                period=period,
                adjust="qfq",
            )
            if not df.empty:
                # filter to requested date
                df["date"] = pd.to_datetime(df["day"]).dt.strftime("%Y-%m-%d %H:%M:%S")
                df = df[df["date"].str.startswith(date)]
                result = pd.DataFrame({
                    "date": df["date"],
                    "open": df["open"].astype(float),
                    "high": df["high"].astype(float),
                    "low": df["low"].astype(float),
                    "close": df["close"].astype(float),
                    "volume": df["volume"].astype(float),
                    "amount": df["amount"].astype(float),
                })
                return result
        except Exception as e:
            logger.error(f"Sina minute({symbol}) fallback also failed: {e}")

        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        import akshare as ak

        try:
            df = await self._run_sync(ak.stock_zh_a_spot_em)
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
            logger.error(f"EastMoney get_realtime_quote failed: {e}")
            return pd.DataFrame(columns=[
                "symbol", "name", "price", "change", "change_pct",
                "volume", "amount", "high", "low", "open", "pre_close",
            ])

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        import akshare as ak

        try:
            pure_symbol = symbol.replace("SH", "").replace("SZ", "").replace(".", "")
            df = await self._run_sync(ak.stock_financial_abstract, symbol=pure_symbol)
            return df
        except Exception as e:
            logger.error(f"EastMoney get_financial_data({symbol}) failed: {e}")
            return pd.DataFrame()

    async def health_check(self) -> bool:
        try:
            import akshare as ak
            await self._run_sync(ak.stock_zh_a_spot_em)
            return True
        except Exception:
            return False
