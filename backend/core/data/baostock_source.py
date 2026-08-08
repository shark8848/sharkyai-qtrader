"""Baostock data source (optional).

Requires the external `baostock` package (pip install baostock). Free,
stable A-share daily/minute data without a token. If baostock is not
installed, health_check() returns False and the source shows as
unavailable in the UI.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import pandas as pd

from qtrader.backend.core.data.base import DataSource

logger = logging.getLogger(__name__)

_BAOSTOCK_AVAILABLE = False
try:
    import baostock as bs  # noqa: F401

    _BAOSTOCK_AVAILABLE = True
except ImportError:
    logger.info("baostock not installed — BaostockSource unavailable")


class BaostockSource(DataSource):
    """Data source backed by Baostock (免费证券数据)."""

    @property
    def name(self) -> str:
        return "Baostock"

    @property
    def source_id(self) -> str:
        return "baostock"

    @property
    def capabilities(self) -> set[str]:
        return {"daily", "minute"} if _BAOSTOCK_AVAILABLE else set()

    @property
    def data_format(self) -> str:
        return "api"

    def _ensure_login(self):
        import baostock as bs

        # baostock uses a process-global session; login is idempotent per process
        lg = bs.login()
        if lg.error_code != "0":
            logger.warning(f"baostock login failed: {lg.error_msg}")

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def get_stock_list(self) -> pd.DataFrame:
        if not _BAOSTOCK_AVAILABLE:
            return pd.DataFrame(columns=["symbol", "name", "market", "industry"])
        try:
            def _fetch():
                import baostock as bs
                self._ensure_login()
                rs = bs.query_all_stock(day="2024-01-01")
                rows = []
                while rs.error_code == "0" and rs.next():
                    r = rs.get_row_data()
                    rows.append(r)
                return rows

            rows = await self._run_sync(_fetch)
            result = pd.DataFrame({
                "symbol": [f"{r[0].split('.')[0].upper()}{r[1]}" for r in rows] if rows else [],
                "name": [r[2] for r in rows] if rows else [],
                "market": ["SH" if r[0].startswith("sh") else "SZ" for r in rows] if rows else [],
                "industry": ["" for _ in rows],
            })
            return result
        except Exception as e:
            logger.error(f"Baostock get_stock_list failed: {e}")
            return pd.DataFrame(columns=["symbol", "name", "market", "industry"])

    async def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        if not _BAOSTOCK_AVAILABLE:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        try:
            # symbol "SH600519" -> "sh.600519"
            code = f"{symbol[:2].lower()}.{symbol[2:]}"

            def _fetch():
                import baostock as bs
                self._ensure_login()
                rs = bs.query_history_k_data_plus(
                    code,
                    "date,open,high,low,close,volume,amount",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    frequency="d",
                    adjustflag="2" if adjust == "qfq" else "1",
                )
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
                return rows

            rows = await self._run_sync(_fetch)
            if not rows:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
            result = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                result[c] = pd.to_numeric(result[c], errors="coerce")
            result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
            return result
        except Exception as e:
            logger.error(f"Baostock get_daily_kline({symbol}) failed: {e}")
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_minute_kline(self, symbol: str, date: str, period: str = "1") -> pd.DataFrame:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    async def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        logger.warning("Baostock source does not provide realtime quotes")
        return pd.DataFrame(columns=[
            "symbol", "name", "price", "change", "change_pct",
            "volume", "amount", "high", "low", "open", "pre_close",
        ])

    async def get_financial_data(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame()

    async def health_check(self) -> bool:
        return _BAOSTOCK_AVAILABLE
