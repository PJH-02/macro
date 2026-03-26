from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.config import AppConfig
from macro_screener.db import SnapshotAlreadyPublishedError, SnapshotRegistry
from macro_screener.models import Snapshot, SnapshotStatus


def ensure_parent(path: Path) -> None:
    """부모 디렉터리가 존재하도록 보장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _sorted_stock_rows(snapshot: Snapshot) -> list[dict[str, Any]]:
    """종목 점수 순 정렬 행을 반환한다."""
    return [stock.to_dict() for stock in snapshot.stock_scores]


def _build_screened_stocks_by_industry(snapshot: Snapshot) -> list[dict[str, Any]]:
    """섹터별 선별 종목 목록을 구성한다. (legacy filename kept)"""
    sector_lookup = {
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
        industry_info = sector_lookup.get(
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


def _build_screened_stocks_by_score(snapshot: Snapshot) -> list[dict[str, Any]]:
    """종목 점수 순 선별 종목 목록을 구성한다."""
    return _sorted_stock_rows(snapshot)


def _normalize_value_for_parquet(value: Any) -> Any:
    """Parquet 직렬화가 어려운 중첩 값을 안정적으로 변환한다."""
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return json.dumps(list(value), ensure_ascii=False, sort_keys=True)
    return value


def _frame_for_parquet(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Parquet 저장 전 중첩 컬럼을 평탄화한다."""
    normalized_rows = [
        {key: _normalize_value_for_parquet(value) for key, value in row.items()}
        for row in rows
    ]
    return pd.DataFrame(normalized_rows)


def _snapshot_artifact_paths(snapshot_root: Path) -> dict[str, Path]:
    """스냅샷 산출물 경로 묶음을 만든다."""
    return {
        "industry_parquet": snapshot_root / "industry_scores.parquet",
        "stock_parquet": snapshot_root / "stock_scores.parquet",
        "industry_csv": snapshot_root / "industry_scores.csv",
        "screened_stock_csv": snapshot_root / "screened_stock_list.csv",
        "screened_stocks_by_score_json": snapshot_root / "screened_stocks_by_score.json",
        "screened_stocks_by_industry_json": snapshot_root / "screened_stocks_by_industry.json",
        "snapshot_json": snapshot_root / "snapshot.json",
    }


def _build_latest_payload(snapshot: Snapshot, artifact_paths: Mapping[str, Path]) -> dict[str, str]:
    """latest 포인터 페이로드를 구성한다."""
    return {
        "run_id": snapshot.run_id,
        "run_type": snapshot.run_type.value,
        "published_at": (
            snapshot.published_at.isoformat() if snapshot.published_at is not None else ""
        ),
        "status": snapshot.status.value,
        **{name: str(path) for name, path in artifact_paths.items()},
    }


def publish_snapshot(
    snapshot: Snapshot,
    output_dir: str | Path,
    *,
    config: AppConfig,
    store: SnapshotRegistry,
    scheduled_window_key: str | None = None,
) -> dict[str, str]:
    """스냅샷 산출물을 저장하고 latest 포인터를 갱신한다."""
    output_dir = Path(output_dir)
    snapshot_root = config.paths.resolve(config.paths.snapshot_dir, output_dir) / snapshot.run_id
    if snapshot_root.exists():
        raise FileExistsError(f"snapshot run already exists: {snapshot.run_id}")
    snapshot_root.mkdir(parents=True, exist_ok=False)
    artifact_paths = _snapshot_artifact_paths(snapshot_root)
    latest_path = config.paths.resolve(config.paths.latest_snapshot_pointer, output_dir)

    stock_rows = _sorted_stock_rows(snapshot)
    industry_rows = [score.to_dict() for score in snapshot.industry_scores]
    industry_frame = pd.DataFrame(industry_rows)
    stock_frame = pd.DataFrame(stock_rows)
    industry_parquet_frame = _frame_for_parquet(industry_rows)
    stock_parquet_frame = _frame_for_parquet(stock_rows)

    industry_parquet_frame.to_parquet(artifact_paths["industry_parquet"], index=False)
    stock_parquet_frame.to_parquet(artifact_paths["stock_parquet"], index=False)
    industry_frame.to_csv(artifact_paths["industry_csv"], index=False, encoding="utf-8-sig")
    stock_frame.to_csv(artifact_paths["screened_stock_csv"], index=False, encoding="utf-8-sig")
    artifact_paths["screened_stocks_by_score_json"].write_text(
        json.dumps(
            _build_screened_stocks_by_score(snapshot),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    artifact_paths["screened_stocks_by_industry_json"].write_text(
        json.dumps(
            _build_screened_stocks_by_industry(snapshot),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    artifact_paths["snapshot_json"].write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    store.write_snapshot(snapshot, snapshot_path=str(artifact_paths["snapshot_json"]))
    if scheduled_window_key is not None and snapshot.status in {
        SnapshotStatus.PUBLISHED,
        SnapshotStatus.INCOMPLETE,
    }:
        try:
            store.register_publication(
                scheduled_window_key=scheduled_window_key,
                run_id=snapshot.run_id,
                published_at=snapshot.published_at or snapshot.as_of_timestamp,
                snapshot_path=str(artifact_paths["snapshot_json"]),
            )
        except SnapshotAlreadyPublishedError:
            shutil.rmtree(snapshot_root, ignore_errors=True)
            raise

    latest_payload = _build_latest_payload(snapshot, artifact_paths)
    if snapshot.status in {SnapshotStatus.PUBLISHED, SnapshotStatus.INCOMPLETE}:
        ensure_parent(latest_path)
        latest_path.write_text(
            json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return latest_payload
