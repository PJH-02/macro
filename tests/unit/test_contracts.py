from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from macro_screener.config import load_config
from macro_screener.db import SnapshotAlreadyPublishedError, SnapshotRegistry
from macro_screener.models import (
    CalendarContext,
    ChannelState,
    IndustryScore,
    RunMetadata,
    RunMode,
    RunType,
    ScheduledWindowKey,
    ScoringContext,
    Snapshot,
    SnapshotStatus,
    Stage1Result,
    StockScore,
)


def test_contracts_round_trip() -> None:
    stage1_result = Stage1Result(
        run_id="run-1",
        run_type=RunType.PRE_OPEN,
        as_of_timestamp=datetime(2026, 3, 21, 8, 30),
        channel_states=[
            ChannelState(channel="G", state=1, effective_at=datetime(2026, 3, 21, 8, 0)),
        ],
        industry_scores=[
            IndustryScore(
                industry_code="101",
                industry_name="Semis",
                base_score=2.0,
                overlay_adjustment=0.5,
                final_score=2.5,
                rank=1,
                negative_penalty=-0.2,
                positive_contribution=1.2,
            )
        ],
        config_version="mvp-1",
        warnings=["stale_dart"],
    )
    scoring_context = ScoringContext(
        run_metadata=RunMetadata(
            run_id="run-1",
            run_type=RunType.PRE_OPEN,
            as_of_timestamp=datetime(2026, 3, 21, 8, 30),
            input_cutoff=datetime(2026, 3, 21, 8, 25),
            scheduled_window_key=ScheduledWindowKey(
                trading_date=date(2026, 3, 21),
                run_type=RunType.PRE_OPEN,
            ),
        ),
        stage1_result=stage1_result,
        config={"config_version": "mvp-1"},
        calendar_context=CalendarContext(
            trading_date=date(2026, 3, 21),
            is_trading_day=True,
            next_trading_date=date(2026, 3, 23),
        ),
        mode=RunMode.SCHEDULED,
        input_cutoff=datetime(2026, 3, 21, 8, 25),
    )
    snapshot = Snapshot(
        run_id="run-1",
        run_type=RunType.PRE_OPEN,
        as_of_timestamp=datetime(2026, 3, 21, 8, 30),
        input_cutoff=datetime(2026, 3, 21, 8, 25),
        published_at=datetime(2026, 3, 21, 8, 31),
        status=SnapshotStatus.PUBLISHED,
        industry_scores=stage1_result.industry_scores,
        stock_scores=[
            StockScore(
                stock_code="005930",
                stock_name="Samsung Electronics",
                industry_code="101",
                final_score=1.8,
                rank=1,
                raw_dart_score=1.2,
                raw_industry_score=0.6,
                normalized_dart_score=0.8,
                normalized_industry_score=0.4,
                block_scores={"supply_contract": 1.2},
                risk_flags=[],
            )
        ],
        warnings=[],
    )

    restored_context = ScoringContext.from_dict(scoring_context.to_dict())
    restored_snapshot = Snapshot.from_dict(snapshot.to_dict())

    assert restored_context.stage1_result.channel_states[0].channel == "G"
    assert restored_snapshot.stock_scores[0].stock_code == "005930"


def test_snapshot_registry_enforces_immutable_scheduled_window(tmp_path: Path) -> None:
    config_path = tmp_path / "config"
    config_path.mkdir(parents=True)
    (config_path / "default.yaml").write_text("{}", encoding="utf-8")
    project_root = tmp_path

    config = load_config(project_root / "config" / "default.yaml")
    registry = SnapshotRegistry.for_config(config=config, base_path=project_root)
    registry.initialize()
    registry.register_publication(
        scheduled_window_key="2026-03-21:pre_open",
        run_id="run-1",
        published_at=datetime(2026, 3, 21, 8, 31),
        snapshot_path="data/snapshots/run-1.parquet",
    )

    with pytest.raises(SnapshotAlreadyPublishedError):
        registry.register_publication(
            scheduled_window_key="2026-03-21:pre_open",
            run_id="run-2",
            published_at=datetime(2026, 3, 21, 8, 32),
            snapshot_path="data/snapshots/run-2.parquet",
        )
