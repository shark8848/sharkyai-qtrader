"""SyncOrchestrator — coordinates sync jobs across sources and targets.

Thin coordination layer on top of the existing sync engines:
  - daily qlib sync  (qlib_sync: akshare/sina -> StandardBar -> .bin)
  - minute sync      (minute_sync: -> parquet)
  - 1min convert     (minute_to_qlib: parquet -> qlib .bin high-freq)

Tracks a lightweight job registry (in-memory) and updates the DataCatalog
after each run so the frontend sees which datasets are ready/stale.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from qtrader.backend.core.data.catalog import data_catalog

logger = logging.getLogger(__name__)

# Valid targets
SYNC_TARGETS = {"qlib_bin", "parquet", "sqlite"}


@dataclass
class SyncJobRecord:
    """In-memory record of a sync job (lightweight, not persisted)."""

    job_id: str
    source_id: str
    market: str
    freq: str
    target: str
    status: str = "pending"       # pending|running|done|error|stopped
    progress: float = 0.0
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
    fail_count: int = 0
    success_count: int = 0
    dataset_id: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "source_id": self.source_id,
            "market": self.market,
            "freq": self.freq,
            "target": self.target,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "fail_count": self.fail_count,
            "success_count": self.success_count,
            "dataset_id": self.dataset_id,
        }


class SyncOrchestrator:
    """Coordinates sync tasks; one engine callback per (source, target)."""

    def __init__(self):
        self._jobs: dict[str, SyncJobRecord] = {}
        self._lock = threading.Lock()
        self._engine = None  # set by register_engine()

    # ------------------------------------------------------------------
    # engine registration
    # ------------------------------------------------------------------
    def register_engine(self, engine):
        """Register the daily sync engine (qlib_sync module) as callable.

        engine must expose:
          start_sync(market, source_id, freq, target) -> dict
          get_status() -> dict
          stop_sync() -> dict
        """
        self._engine = engine

    # ------------------------------------------------------------------
    # job management
    # ------------------------------------------------------------------
    def submit(
        self,
        source_id: str,
        market: str,
        freq: str,
        target: str,
    ) -> dict:
        """Submit a sync job. Returns the job record dict."""
        if target not in SYNC_TARGETS:
            return {"error": f"不支持的目标存储: {target} (可选: {sorted(SYNC_TARGETS)})"}

        job_id = f"sync_{uuid.uuid4().hex[:12]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = SyncJobRecord(
            job_id=job_id,
            source_id=source_id,
            market=market,
            freq=freq,
            target=target,
            status="pending",
            started_at=now,
        )

        # run the actual engine synchronously in a daemon thread
        def _run():
            try:
                if self._engine is None:
                    record.status = "error"
                    record.message = "同步引擎未注册"
                    return
                record.status = "running"
                result = self._engine.start_sync(
                    market=market, source_id=source_id, freq=freq, target=target
                )
                if result.get("error"):
                    record.status = "error"
                    record.message = result["error"]
                    return
                # engine runs in its own thread; poll until done
                _status_fn = getattr(self._engine, "get_status", None) or getattr(
                    self._engine, "get_sync_status", None
                )
                while True:
                    st = _status_fn()
                    record.progress = st.get("progress", 0)
                    record.message = st.get("message", "")
                    record.success_count = st.get("success_stocks", 0)
                    record.fail_count = st.get("fail_stocks", 0)
                    if st.get("status") in ("done", "error"):
                        break
                    import time

                    time.sleep(3)
                record.status = st.get("status", "done")
                record.progress = 100.0
                record.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # update catalog
                self._record_catalog(record, st)
            except Exception as e:
                record.status = "error"
                record.message = str(e)
                logger.exception(f"Sync job {job_id} failed")

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        with self._lock:
            self._jobs[job_id] = record
        return record.to_dict()

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()]

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(job_id)
            return j.to_dict() if j else None

    # ------------------------------------------------------------------
    # catalog
    # ------------------------------------------------------------------
    def _record_catalog(self, record: SyncJobRecord, engine_status: dict):
        """Write a dataset_catalog row after a successful sync."""
        if record.status != "done":
            return
        dataset_id = data_catalog.dataset_id_for(record.market, record.freq, record.source_id)
        record.dataset_id = dataset_id
        # engine_status carries coverage info if the engine provides it
        data_catalog.upsert(
            dataset_id=dataset_id,
            source_id=record.source_id,
            market=record.market,
            freq=record.freq,
            storage=record.target,
            stock_count=engine_status.get("overall_synced", 0),
            coverage_pct=engine_status.get("overall_pct", 0.0),
            start_date=engine_status.get("data_start", ""),
            end_date=engine_status.get("data_end", ""),
            status="ready",
        )
        logger.info(f"Catalog updated: {dataset_id}")


# Singleton
orchestrator = SyncOrchestrator()
