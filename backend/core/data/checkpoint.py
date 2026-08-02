"""Sync checkpoint manager.

Provides real-time checkpoint persistence so that sync tasks can resume
from exactly where they left off after a restart.

Checkpoint files:
    ~/.qtrader/checkpoint_daily.json
    ~/.qtrader/checkpoint_minute.json

Each checkpoint records the set of completed stock symbols for the current
sync run. Updated after every stock (buffered write every 5 stocks for I/O
efficiency). Cleared on sync completion.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path.home() / ".qtrader"


class SyncCheckpoint:
    """Manages checkpoint state for a sync task."""

    def __init__(self, task_name: str):
        """
        Args:
            task_name: 'daily' or 'minute'
        """
        self.path = CHECKPOINT_DIR / f"checkpoint_{task_name}.json"
        self.completed: set[str] = set()
        self.started_at: str = ""
        self._buffer_count = 0
        self._buffer_limit = 5  # flush every N stocks

    def load(self) -> set[str]:
        """Load checkpoint from disk. Returns set of completed symbols."""
        if not self.path.exists():
            self.completed = set()
            return self.completed
        try:
            data = json.loads(self.path.read_text())
            self.completed = set(data.get("completed", []))
            self.started_at = data.get("started_at", "")
            logger.info(f"Checkpoint loaded: {len(self.completed)} completed stocks")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            self.completed = set()
        return self.completed

    def start(self):
        """Initialize a new sync run (clear previous checkpoint)."""
        self.completed = set()
        self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._flush()

    def mark_done(self, symbol: str):
        """Mark a stock as completed. Buffered write."""
        self.completed.add(symbol.lower())
        self._buffer_count += 1
        if self._buffer_count >= self._buffer_limit:
            self._flush()
            self._buffer_count = 0

    def is_done(self, symbol: str) -> bool:
        """Check if a stock was already completed in this run."""
        return symbol.lower() in self.completed

    def finish(self):
        """Sync completed successfully — remove checkpoint file."""
        self.completed = set()
        if self.path.exists():
            self.path.unlink()
        logger.info("Checkpoint cleared (sync finished)")

    def _flush(self):
        """Write current state to disk."""
        data = {
            "started_at": self.started_at,
            "completed": sorted(self.completed),
            "count": len(self.completed),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to write checkpoint: {e}")

    @property
    def count(self) -> int:
        return len(self.completed)
