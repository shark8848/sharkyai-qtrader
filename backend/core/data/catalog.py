"""DataCatalog — metadata registry for datasets.

Records every synced dataset (market x freq x source) with coverage and
freshness so the frontend can show which data is ready for training and
which is stale.

Stored in the same SQLite db as job_store (~/.qtrader/jobs.db) under the
`dataset_catalog` table.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from qtrader.backend.config import settings

logger = logging.getLogger(__name__)

_CATALOG_DB = Path.home() / ".qtrader" / "jobs.db"


class DataCatalog:
    """Dataset metadata store."""

    def __init__(self, db_path: str | None = None):
        self._db_path = Path(db_path or _CATALOG_DB)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_catalog (
                    dataset_id     TEXT PRIMARY KEY,
                    source_id      TEXT NOT NULL,
                    market         TEXT NOT NULL,
                    freq           TEXT NOT NULL,
                    storage        TEXT NOT NULL DEFAULT 'qlib_bin',
                    start_date     TEXT,
                    end_date       TEXT,
                    stock_count    INTEGER DEFAULT 0,
                    coverage_pct   REAL DEFAULT 0,
                    adjusted       TEXT DEFAULT 'hfq',
                    synced_at      TEXT,
                    status         TEXT DEFAULT 'syncing'
                )
                """
            )

    # ------------------------------------------------------------------
    # upsert / query
    # ------------------------------------------------------------------
    def upsert(
        self,
        dataset_id: str,
        source_id: str,
        market: str,
        freq: str,
        storage: str = "qlib_bin",
        start_date: str = "",
        end_date: str = "",
        stock_count: int = 0,
        coverage_pct: float = 0.0,
        adjusted: str = "hfq",
        status: str = "syncing",
    ):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dataset_catalog
                (dataset_id, source_id, market, freq, storage, start_date,
                 end_date, stock_count, coverage_pct, adjusted, synced_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    dataset_id,
                    source_id,
                    market,
                    freq,
                    storage,
                    start_date,
                    end_date,
                    stock_count,
                    coverage_pct,
                    adjusted,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status,
                ),
            )

    def mark_status(self, dataset_id: str, status: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE dataset_catalog SET status=?, synced_at=? WHERE dataset_id=?",
                (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dataset_id),
            )

    def get(self, dataset_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dataset_catalog WHERE dataset_id=?", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dataset_catalog ORDER BY synced_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, dataset_id: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM dataset_catalog WHERE dataset_id=?", (dataset_id,))

    # ------------------------------------------------------------------
    # freshness
    # ------------------------------------------------------------------
    @staticmethod
    def is_stale(synced_at: str, tolerance_days: int = 2) -> bool:
        """A dataset is stale if last synced more than tolerance_days ago."""
        if not synced_at:
            return True
        try:
            ts = datetime.strptime(synced_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return True
        return (datetime.now() - ts) > timedelta(days=tolerance_days)

    def annotate_freshness(self, datasets: list[dict]) -> list[dict]:
        """Add 'stale' flag to each dataset dict."""
        for d in datasets:
            d["stale"] = self.is_stale(d.get("synced_at", ""))
        return datasets

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def dataset_id_for(self, market: str, freq: str, source_id: str) -> str:
        """Deterministic dataset id: {market}_{freq}_{source_id}_{YYYYMMDD}."""
        return f"{market}_{freq}_{source_id}_{datetime.now().strftime('%Y%m%d')}"


# Singleton
data_catalog = DataCatalog()
