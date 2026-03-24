from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from macro_screener.config import load_config
from macro_screener.db import SnapshotRegistry
from macro_screener.models import IndustryScore, RunType, Snapshot, SnapshotStatus, StockScore
from macro_screener.pipeline.publisher import publish_snapshot


def _snapshot() -> Snapshot:
    as_of = datetime.fromisoformat("2026-03-24T08:30:00+09:00")
    return Snapshot(
        run_id="screening-view-test",
        run_type=RunType.MANUAL,
        as_of_timestamp=as_of,
        input_cutoff=as_of,
        published_at=as_of,
        status=SnapshotStatus.PUBLISHED,
        industry_scores=[
            IndustryScore(
                industry_code="BETA",
                industry_name="Beta",
                base_score=2.0,
                overlay_adjustment=0.0,
                final_score=2.0,
                rank=1,
            ),
            IndustryScore(
                industry_code="ALPHA",
                industry_name="Alpha",
                base_score=1.0,
                overlay_adjustment=0.0,
                final_score=1.0,
                rank=2,
            ),
        ],
        stock_scores=[
            StockScore(
                stock_code="000002",
                stock_name="Second",
                industry_code="ALPHA",
                final_score=1.5,
                rank=1,
                raw_dart_score=1.0,
                raw_industry_score=1.0,
                normalized_dart_score=1.0,
                normalized_industry_score=1.0,
                block_scores={"supply_contract": 1.0},
            ),
            StockScore(
                stock_code="000001",
                stock_name="First",
                industry_code="BETA",
                final_score=0.5,
                rank=2,
                raw_dart_score=0.0,
                raw_industry_score=2.0,
                normalized_dart_score=0.0,
                normalized_industry_score=1.0,
                block_scores={"supply_contract": 0.0},
            ),
        ],
    )


def test_publish_snapshot_keeps_industry_view_and_adds_score_sorted_view(tmp_path: Path) -> None:
    config = load_config()
    store = SnapshotRegistry(tmp_path / "data" / "macro_screener.sqlite3")

    latest = publish_snapshot(
        _snapshot(),
        tmp_path,
        config=config,
        store=store,
    )

    score_view_path = Path(latest["screened_stocks_by_score_json"])
    industry_view_path = Path(latest["screened_stocks_by_industry_json"])

    score_view = json.loads(score_view_path.read_text(encoding="utf-8"))
    industry_view = json.loads(industry_view_path.read_text(encoding="utf-8"))

    assert [item["stock_code"] for item in score_view] == ["000002", "000001"]
    assert [bucket["industry_code"] for bucket in industry_view] == ["BETA", "ALPHA"]
    assert [item["stock_code"] for item in industry_view[0]["stocks"]] == ["000001"]
    assert [item["stock_code"] for item in industry_view[1]["stocks"]] == ["000002"]
