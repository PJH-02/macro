from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from macro_screener.config import AppConfig
from macro_screener.models import ChannelState, Snapshot

SCHEMA_VERSION = 1
CHANNEL_STATE_METADATA_DEFAULT = "{}"


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
                metadata_json TEXT NOT NULL DEFAULT '{}',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._ensure_column(
            connection,
            table_name="channel_state_snapshots",
            column_name="metadata_json",
            definition="TEXT NOT NULL DEFAULT '{}'",
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_state_effective_at "
            "ON channel_state_snapshots (effective_at DESC)"
        )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        *,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(str(row["name"]) == column_name for row in rows):
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
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

    def get_watermark_payload(
        self,
        *,
        source_name: str,
        resource_key: str,
    ) -> dict[str, Any] | None:
        watermark_value = self.get_watermark(source_name=source_name, resource_key=resource_key)
        if watermark_value is None:
            return None
        try:
            payload = json.loads(watermark_value)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def upsert_watermark_payload(
        self,
        *,
        source_name: str,
        resource_key: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.upsert_watermark(
            source_name=source_name,
            resource_key=resource_key,
            watermark_value=json.dumps(dict(payload), ensure_ascii=False, sort_keys=True),
        )

    def save_channel_states(
        self,
        *,
        run_id: str,
        channel_states: list[ChannelState],
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not channel_states:
            return
        payload_json = json.dumps([state.to_dict() for state in channel_states], ensure_ascii=False)
        effective_at = max(state.effective_at for state in channel_states).isoformat()
        metadata_payload = self._build_channel_state_metadata(
            channel_states=channel_states,
            source=source,
            metadata=metadata,
        )
        metadata_json = json.dumps(metadata_payload, ensure_ascii=False, sort_keys=True)
        source_text = str(
            metadata_payload.get("source_name")
            or metadata_payload.get("source")
            or source
            or self._channel_state_source(channel_states[0])
        )
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO channel_state_snapshots (
                    run_id,
                    effective_at,
                    source,
                    metadata_json,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, effective_at, source_text, metadata_json, payload_json, created_at),
            )
            connection.commit()

    @staticmethod
    def _channel_state_source(state: ChannelState) -> str:
        source_name = getattr(state, "source_name", None)
        if source_name is not None:
            return str(source_name)
        return str(getattr(state, "source", "manual"))

    @classmethod
    def _build_channel_state_metadata(
        cls,
        *,
        channel_states: list[ChannelState],
        source: str | None,
        metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        first_state = channel_states[0]
        warning_flags: list[str] = []
        confidence_by_channel: dict[str, float] = {}
        for state in channel_states:
            channel = str(state.channel)
            confidence = getattr(state, "confidence", None)
            if confidence is not None:
                confidence_by_channel[channel] = float(confidence)
            for warning in getattr(state, "warning_flags", []):
                warning_text = str(warning)
                if warning_text not in warning_flags:
                    warning_flags.append(warning_text)
        derived: dict[str, Any] = {
            "source_name": cls._channel_state_source(first_state),
            "source_version": getattr(first_state, "source_version", None),
            "fallback_mode": getattr(first_state, "fallback_mode", None),
            "as_of_timestamp": cls._datetime_attr(first_state, "as_of_timestamp"),
            "input_cutoff": cls._datetime_attr(first_state, "input_cutoff"),
            "warning_flags": warning_flags,
        }
        if source is not None:
            derived["source_name"] = source
        if confidence_by_channel:
            derived["confidence_by_channel"] = confidence_by_channel
        if metadata is not None:
            for key, value in metadata.items():
                derived[str(key)] = value
        return derived

    @staticmethod
    def _datetime_attr(state: ChannelState, attr_name: str) -> str | None:
        value = getattr(state, attr_name, None)
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def load_last_channel_state_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT payload_json, metadata_json
                FROM channel_state_snapshots
                ORDER BY effective_at DESC, record_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload_json"]))
        metadata_raw = row["metadata_json"]
        metadata_payload = (
            json.loads(str(metadata_raw))
            if metadata_raw not in (None, "", CHANNEL_STATE_METADATA_DEFAULT)
            else {}
        )
        metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
        return {
            "channel_states": [ChannelState.from_dict(item) for item in payload],
            "metadata": metadata,
        }

    def load_last_channel_states(self) -> list[ChannelState] | None:
        snapshot = self.load_last_channel_state_snapshot()
        if snapshot is None:
            return None
        return cast(list[ChannelState], snapshot["channel_states"])
