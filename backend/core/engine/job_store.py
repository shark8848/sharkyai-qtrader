"""
JobStore: 训练任务持久化存储层
支持 SQLite（默认）和 PostgreSQL 后端
"""
import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class JobStore(ABC):
    """训练任务存储抽象接口"""

    @abstractmethod
    def save_job(self, data: dict) -> None:
        """保存/更新任务（data 为 TrainJob.to_dict() 的输出）"""
        ...

    @abstractmethod
    def load_job(self, job_id: str) -> Optional[dict]:
        """加载单个任务"""
        ...

    @abstractmethod
    def load_all_jobs(self) -> list[dict]:
        """加载全部任务"""
        ...

    @abstractmethod
    def delete_job(self, job_id: str) -> None:
        """删除任务"""
        ...


# ---------------------------------------------------------------------------
# SQLite 实现
# ---------------------------------------------------------------------------

class SQLiteJobStore(JobStore):
    """基于 SQLite 的任务存储"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".qtrader" / "jobs.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS train_jobs (
                    job_id      TEXT PRIMARY KEY,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    config      TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    finished_at TEXT,
                    error       TEXT,
                    metrics     TEXT,
                    progress    INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL DEFAULT '',
                    logs        TEXT NOT NULL DEFAULT '[]',
                    model_path  TEXT
                )
            """)
            conn.commit()
            conn.close()
        logger.info(f"SQLiteJobStore initialized: {self._db_path}")

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def save_job(self, data: dict) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("""
                INSERT OR REPLACE INTO train_jobs
                    (job_id, status, config, created_at, finished_at, error,
                     metrics, progress, current_step, logs, model_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["job_id"],
                data["status"],
                json.dumps(data.get("config", {}), ensure_ascii=False),
                data.get("created_at", ""),
                data.get("finished_at"),
                data.get("error"),
                json.dumps(data.get("metrics"), ensure_ascii=False) if data.get("metrics") else None,
                data.get("progress", 0),
                data.get("current_step", ""),
                json.dumps(data.get("logs", []), ensure_ascii=False),
                data.get("model_path"),
            ))
            conn.commit()
            conn.close()

    def load_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM train_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            conn.close()
            if row is None:
                return None
            return self._row_to_dict(row)

    def load_all_jobs(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM train_jobs ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM train_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            conn.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        # JSON 字段反序列化
        for key in ("config", "metrics", "logs"):
            if d.get(key) and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d


# ---------------------------------------------------------------------------
# PostgreSQL 实现
# ---------------------------------------------------------------------------

class PostgresJobStore(JobStore):
    """基于 PostgreSQL 的任务存储"""

    def __init__(self, dsn: str):
        """
        dsn 格式: postgresql://user:pass@host:5432/dbname
                  或 postgresql+psycopg2://...
        """
        import psycopg2
        self._dsn = dsn.replace("+psycopg2", "").replace("+asyncpg", "")
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(self._dsn)
        conn.autocommit = False
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS train_jobs (
                    job_id       TEXT PRIMARY KEY,
                    status       TEXT NOT NULL DEFAULT 'pending',
                    config       JSONB NOT NULL DEFAULT '{}',
                    created_at   TEXT NOT NULL,
                    finished_at  TEXT,
                    error        TEXT,
                    metrics      JSONB,
                    progress     INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL DEFAULT '',
                    logs         JSONB NOT NULL DEFAULT '[]',
                    model_path   TEXT
                )
            """)
            conn.commit()
            cur.close()
            conn.close()
        logger.info(f"PostgresJobStore initialized: {self._dsn.split('@')[-1] if '@' in self._dsn else '***'}")

    def save_job(self, data: dict) -> None:
        import psycopg2
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO train_jobs
                    (job_id, status, config, created_at, finished_at, error,
                     metrics, progress, current_step, logs, model_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status       = EXCLUDED.status,
                    finished_at  = EXCLUDED.finished_at,
                    error        = EXCLUDED.error,
                    metrics      = EXCLUDED.metrics,
                    progress     = EXCLUDED.progress,
                    current_step = EXCLUDED.current_step,
                    logs         = EXCLUDED.logs,
                    model_path   = EXCLUDED.model_path
            """, (
                data["job_id"],
                data["status"],
                json.dumps(data.get("config", {}), ensure_ascii=False),
                data.get("created_at", ""),
                data.get("finished_at"),
                data.get("error"),
                json.dumps(data.get("metrics"), ensure_ascii=False) if data.get("metrics") else None,
                data.get("progress", 0),
                data.get("current_step", ""),
                json.dumps(data.get("logs", []), ensure_ascii=False),
                data.get("model_path"),
            ))
            conn.commit()
            cur.close()
            conn.close()

    def load_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT * FROM train_jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
            cols = [desc[0] for desc in cur.description]
            cur.close()
            conn.close()
            if row is None:
                return None
            return self._row_to_dict(dict(zip(cols, row)))

    def load_all_jobs(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT * FROM train_jobs ORDER BY created_at DESC")
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            cur.close()
            conn.close()
            return [self._row_to_dict(dict(zip(cols, r))) for r in rows]

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM train_jobs WHERE job_id = %s", (job_id,))
            conn.commit()
            cur.close()
            conn.close()

    @staticmethod
    def _row_to_dict(d: dict) -> dict:
        # psycopg2 对 JSONB 列自动反序列化为 dict/list
        for key in ("config", "metrics", "logs"):
            if d.get(key) and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_job_store(backend: str = "sqlite", **kwargs) -> JobStore:
    """
    创建 JobStore 实例

    Args:
        backend: "sqlite" 或 "postgresql"
        **kwargs:
            sqlite:    db_path (可选，默认 ~/.qtrader/jobs.db)
            postgresql: dsn (必填，如 postgresql://user:pass@host/db)
    """
    if backend in ("postgresql", "postgres", "pg"):
        dsn = kwargs.get("dsn") or kwargs.get("db_url", "")
        if not dsn:
            raise ValueError("PostgreSQL backend requires 'dsn' or 'db_url' parameter")
        return PostgresJobStore(dsn=dsn)
    else:
        return SQLiteJobStore(db_path=kwargs.get("db_path"))
