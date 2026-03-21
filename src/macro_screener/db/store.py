from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from macro_screener.config import AppConfig


class SnapshotAlreadyPublishedError(RuntimeError):
    """Raised when a scheduled window already has a published snapshot."""


@dataclass(frozen=True, slots=True)
class SnapshotRegistry:
    sqlite_path: Path

    @classmethod
    def for_config(cls, config: AppConfig, base_path: Path) -> "SnapshotRegistry":
        return cls(sqlite_path=config.paths.resolve(config.paths.sqlite_path, base_path))

    def initialize(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS published_snapshots (
                    scheduled_window_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    published_at TEXT NOT NULL,
                    snapshot_path TEXT
                )
                """
            )
            connection.commit()

    def register_publication(
        self,
        *,
        scheduled_window_key: str,
        run_id: str,
        published_at: datetime,
        snapshot_path: str | None = None,
    ) -> None:
        self.initialize()
        try:
            with sqlite3.connect(self.sqlite_path) as connection:
                connection.execute(
                    """
                    INSERT INTO published_snapshots (
                        scheduled_window_key,
                        run_id,
                        published_at,
                        snapshot_path
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (scheduled_window_key, run_id, published_at.isoformat(), snapshot_path),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SnapshotAlreadyPublishedError(
                f"Scheduled window already published: {scheduled_window_key}"
            ) from exc
