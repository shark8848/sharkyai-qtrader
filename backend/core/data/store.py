"""Local SQLite storage layer for caching fetched data."""

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

from qtrader.backend.config import settings


class DataStore:
    """SQLite-based local cache for market data.

    Stores daily kline data and stock lists to avoid redundant API calls.
    Supports incremental updates by tracking the latest cached date per symbol.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path(settings.data_dir) / "cache.db")
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kline_cache (
                    symbol TEXT,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    amount REAL,
                    source TEXT,
                    PRIMARY KEY (symbol, date, source)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_list_cache (
                    symbol TEXT,
                    name TEXT,
                    market TEXT,
                    industry TEXT,
                    source TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (symbol, source)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kline_symbol_date
                ON kline_cache(symbol, date)
            """)

    def save_kline(self, df: pd.DataFrame, symbol: str, source: str):
        """Save kline DataFrame to cache (upsert)."""
        if df.empty:
            return
        records = df.copy()
        records["symbol"] = symbol
        records["source"] = source
        with self._get_conn() as conn:
            records.to_sql("kline_cache", conn, if_exists="append", index=False,
                           method=_upsert_kline)

    def load_kline(
        self, symbol: str, start_date: str, end_date: str, source: str
    ) -> pd.DataFrame:
        """Load cached kline data for a symbol and date range."""
        with self._get_conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume, amount "
                "FROM kline_cache WHERE symbol=? AND date>=? AND date<=? AND source=? "
                "ORDER BY date",
                conn,
                params=(symbol, start_date, end_date, source),
            )
        return df

    def get_latest_cached_date(self, symbol: str, source: str) -> Optional[str]:
        """Get the latest cached date for a symbol."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT MAX(date) FROM kline_cache WHERE symbol=? AND source=?",
                (symbol, source),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None

    def save_stock_list(self, df: pd.DataFrame, source: str):
        """Save stock list to cache (replace)."""
        if df.empty:
            return
        records = df.copy()
        records["source"] = source
        import datetime
        records["updated_at"] = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("DELETE FROM stock_list_cache WHERE source=?", (source,))
            records.to_sql("stock_list_cache", conn, if_exists="append", index=False)

    def load_stock_list(self, source: str) -> pd.DataFrame:
        """Load cached stock list."""
        with self._get_conn() as conn:
            df = pd.read_sql_query(
                "SELECT symbol, name, market, industry FROM stock_list_cache WHERE source=?",
                conn,
                params=(source,),
            )
        return df


def _upsert_kline(table, conn, keys, data_iter):
    """Custom pandas to_sql method for upsert (INSERT OR REPLACE)."""
    for row in data_iter:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} "
            f"({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            row,
        )


# Singleton
data_store = DataStore()
