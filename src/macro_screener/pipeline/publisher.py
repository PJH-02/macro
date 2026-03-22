from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.config import AppConfig
from macro_screener.db import SnapshotAlreadyPublishedError, SnapshotRegistry
from macro_screener.models import Snapshot, SnapshotStatus


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _build_screened_stocks_by_industry(snapshot: Snapshot) -> list[dict[str, Any]]:
    industry_lookup = {
        score.industry_code: {
            "industry_code": score.industry_code,
            "industry_name": score.industry_name,
            "industry_rank": score.rank,
            "industry_score": score.final_score,
        }
        for score in snapshot.industry_scores
    }
    grouped: dict[str, dict[str, Any]] = {}
    for stock in snapshot.stock_scores:
        industry_info = industry_lookup.get(
            stock.industry_code,
            {
                "industry_code": stock.industry_code,
                "industry_name": stock.industry_code,
                "industry_rank": None,
                "industry_score": None,
            },
        )
        bucket = grouped.setdefault(
            stock.industry_code,
            {
                **industry_info,
                "stocks": [],
            },
        )
        bucket["stocks"].append(stock.to_dict())

    ranked_groups = sorted(
        grouped.values(),
        key=lambda item: (
            item["industry_rank"] is None,
            item["industry_rank"] if item["industry_rank"] is not None else 10**9,
            str(item["industry_code"]),
        ),
    )
    for bucket in ranked_groups:
        bucket["stocks"] = sorted(
            bucket["stocks"],
            key=lambda item: (int(item["rank"]), str(item["stock_code"])),
        )
    return ranked_groups


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
    industry_csv_path = snapshot_root / "industry_scores.csv"
    screened_stock_csv_path = snapshot_root / "screened_stock_list.csv"
    screened_by_industry_json_path = snapshot_root / "screened_stocks_by_industry.json"
    snapshot_json_path = snapshot_root / "snapshot.json"
    latest_path = config.paths.resolve(config.paths.latest_snapshot_pointer, output_dir)

    industry_frame = pd.DataFrame([score.to_dict() for score in snapshot.industry_scores])
    stock_frame = pd.DataFrame([score.to_dict() for score in snapshot.stock_scores])

    industry_frame.to_parquet(
        industry_path, index=False
    )
    stock_frame.to_parquet(
        stock_path, index=False
    )
    industry_frame.to_csv(industry_csv_path, index=False, encoding="utf-8-sig")
    stock_frame.to_csv(screened_stock_csv_path, index=False, encoding="utf-8-sig")
    screened_by_industry_json_path.write_text(
        json.dumps(
            _build_screened_stocks_by_industry(snapshot),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
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
        "industry_csv": str(industry_csv_path),
        "screened_stock_csv": str(screened_stock_csv_path),
        "screened_stocks_by_industry_json": str(screened_by_industry_json_path),
    }
    if snapshot.status in {SnapshotStatus.PUBLISHED, SnapshotStatus.INCOMPLETE}:
        ensure_parent(latest_path)
        latest_path.write_text(
            json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return latest_payload
