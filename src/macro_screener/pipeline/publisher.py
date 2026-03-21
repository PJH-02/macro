from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.config import AppConfig
from macro_screener.db import SnapshotAlreadyPublishedError, SnapshotRegistry
from macro_screener.models import Snapshot, SnapshotStatus


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def publish_snapshot(
    snapshot: Snapshot,
    output_dir: str | Path,
    *,
    config: AppConfig,
    store: SnapshotRegistry,
    scheduled_window_key: str | None = None,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    snapshot_root = config.paths.resolve(config.paths.snapshot_dir, output_dir) / snapshot.run_id
    if snapshot_root.exists():
        raise FileExistsError(f"snapshot run already exists: {snapshot.run_id}")
    snapshot_root.mkdir(parents=True, exist_ok=False)

    industry_path = snapshot_root / "industry_scores.parquet"
    stock_path = snapshot_root / "stock_scores.parquet"
    snapshot_json_path = snapshot_root / "snapshot.json"
    latest_path = config.paths.resolve(config.paths.latest_snapshot_pointer, output_dir)

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

    store.write_snapshot(snapshot, snapshot_path=str(snapshot_json_path))
    if scheduled_window_key is not None and snapshot.status in {
        SnapshotStatus.PUBLISHED,
        SnapshotStatus.INCOMPLETE,
    }:
        try:
            store.register_publication(
                scheduled_window_key=scheduled_window_key,
                run_id=snapshot.run_id,
                published_at=snapshot.published_at or snapshot.as_of_timestamp,
                snapshot_path=str(snapshot_json_path),
            )
        except SnapshotAlreadyPublishedError:
            shutil.rmtree(snapshot_root, ignore_errors=True)
            raise

    latest_payload = {
        "run_id": snapshot.run_id,
        "run_type": snapshot.run_type.value,
        "published_at": (
            snapshot.published_at.isoformat() if snapshot.published_at is not None else ""
        ),
        "status": snapshot.status.value,
        "snapshot_json": str(snapshot_json_path),
        "industry_parquet": str(industry_path),
        "stock_parquet": str(stock_path),
    }
    if snapshot.status in {SnapshotStatus.PUBLISHED, SnapshotStatus.INCOMPLETE}:
        ensure_parent(latest_path)
        latest_path.write_text(
            json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return latest_payload
