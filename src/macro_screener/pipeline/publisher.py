from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from macro_screener.contracts import Snapshot


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_sqlite(snapshot: Snapshot, database_path: Path) -> None:
    ensure_parent(database_path)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                input_cutoff TEXT NOT NULL,
                published_at TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO snapshots (
                run_id, run_type, as_of_timestamp, input_cutoff, published_at, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.run_id,
                snapshot.run_type,
                snapshot.as_of_timestamp,
                snapshot.input_cutoff,
                snapshot.published_at,
                snapshot.status,
                json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def publish_snapshot(snapshot: Snapshot, output_dir: str | Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    snapshot_root = output_dir / "data" / "snapshots" / snapshot.run_id
    if snapshot_root.exists():
        raise FileExistsError(f"snapshot run already exists: {snapshot.run_id}")
    snapshot_root.mkdir(parents=True, exist_ok=False)

    industry_path = snapshot_root / "industry_scores.parquet"
    stock_path = snapshot_root / "stock_scores.parquet"
    snapshot_json_path = snapshot_root / "snapshot.json"
    latest_path = output_dir / "data" / "snapshots" / "latest.json"
    database_path = output_dir / "data" / "snapshots" / "mvp.sqlite"

    pd.DataFrame([score.to_dict() for score in snapshot.industry_scores]).to_parquet(
        industry_path, index=False
    )
    pd.DataFrame([score.to_dict() for score in snapshot.stock_scores]).to_parquet(
        stock_path, index=False
    )
    snapshot_json_path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_sqlite(snapshot, database_path)

    latest_payload = {
        "run_id": snapshot.run_id,
        "run_type": snapshot.run_type,
        "published_at": snapshot.published_at,
        "snapshot_json": str(snapshot_json_path),
        "industry_parquet": str(industry_path),
        "stock_parquet": str(stock_path),
    }
    ensure_parent(latest_path)
    latest_path.write_text(
        json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {key: str(value) for key, value in latest_payload.items()}
