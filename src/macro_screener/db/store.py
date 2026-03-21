from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from macro_screener.config import AppConfig
from macro_screener.models import ChannelState, Snapshot

SCHEMA_VERSION = 1


class SnapshotAlreadyPublishedError(RuntimeError):
    """Raised when a scheduled window already has a published snapshot."""


@dataclass(frozen=True, slots=True)
class SnapshotRegistry:
    sqlite_path: Path

    @classmethod
    def for_config(cls, config: AppConfig, base_path: Path) -> "SnapshotRegistry":
        return cls(sqlite_path=config.paths.resolve(config.paths.sqlite_path, base_path))

    def connect(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            connection.commit()

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                schema_version INTEGER NOT NULL
            )
            """
        )
        row = connection.execute(
            "SELECT schema_version FROM schema_meta ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO schema_meta (schema_version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        elif int(row["schema_version"]) != SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported SQLite schema version: {row['schema_version']} != {SCHEMA_VERSION}"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                input_cutoff TEXT NOT NULL,
                published_at TEXT,
                status TEXT NOT NULL,
                snapshot_path TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_watermarks (
                source_name TEXT NOT NULL,
                resource_key TEXT NOT NULL,
                watermark_value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_name, resource_key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_state_snapshots (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                effective_at TEXT NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_state_effective_at "
            "ON channel_state_snapshots (effective_at DESC)"
        )

    def write_snapshot(self, snapshot: Snapshot, *, snapshot_path: str | None = None) -> None:
        payload_json = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO snapshots (
                    run_id,
                    run_type,
                    as_of_timestamp,
                    input_cutoff,
                    published_at,
                    status,
                    snapshot_path,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.run_id,
                    snapshot.run_type.value,
                    snapshot.as_of_timestamp.isoformat(),
                    snapshot.input_cutoff.isoformat(),
                    (
                        snapshot.published_at.isoformat()
                        if snapshot.published_at is not None
                        else None
                    ),
                    snapshot.status.value,
                    snapshot_path,
                    payload_json,
                    created_at,
                ),
            )
            connection.commit()

    def published_snapshot_for_window(self, scheduled_window_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT scheduled_window_key, run_id, published_at, snapshot_path
                FROM published_snapshots
                WHERE scheduled_window_key = ?
                """,
                (scheduled_window_key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def register_publication(
        self,
        *,
        scheduled_window_key: str,
        run_id: str,
        published_at: datetime,
        snapshot_path: str | None = None,
    ) -> None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            try:
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

    def get_watermark(self, *, source_name: str, resource_key: str) -> str | None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT watermark_value
                FROM ingestion_watermarks
                WHERE source_name = ? AND resource_key = ?
                """,
                (source_name, resource_key),
            ).fetchone()
        return None if row is None else str(row["watermark_value"])

    def upsert_watermark(
        self,
        *,
        source_name: str,
        resource_key: str,
        watermark_value: str,
    ) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO ingestion_watermarks (
                    source_name,
                    resource_key,
                    watermark_value,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(source_name, resource_key) DO UPDATE SET
                    watermark_value = excluded.watermark_value,
                    updated_at = excluded.updated_at
                """,
                (source_name, resource_key, watermark_value, updated_at),
            )
            connection.commit()

    def save_channel_states(
        self,
        *,
        run_id: str,
        channel_states: list[ChannelState],
        source: str,
    ) -> None:
        if not channel_states:
            return
        payload_json = json.dumps([state.to_dict() for state in channel_states], ensure_ascii=False)
        effective_at = max(state.effective_at for state in channel_states).isoformat()
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO channel_state_snapshots (
                    run_id,
                    effective_at,
                    source,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, effective_at, source, payload_json, created_at),
            )
            connection.commit()

    def load_last_channel_states(self) -> list[ChannelState] | None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT payload_json
                FROM channel_state_snapshots
                ORDER BY effective_at DESC, record_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload_json"]))
        return [ChannelState.from_dict(item) for item in payload]
