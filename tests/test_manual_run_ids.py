from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from macro_screener.data.dart_client import DARTLoadResult
from macro_screener.data.krx_client import KRXLoadResult
from macro_screener.models import ChannelState, IndustryScore, RunType, SnapshotStatus, Stage1Result
from macro_screener.pipeline.runner import build_manual_context, run_manual
from macro_screener.serialization import parse_datetime


@dataclass
class _StoreStub:
    def published_snapshot_for_window(self, key: str) -> None:
        return None

    def save_channel_states(
        self,
        *,
        run_id: str,
        channel_states: list[ChannelState],
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None


@dataclass
class _BootstrapStub:
    store: _StoreStub


def _stage1_result(
    run_id: str,
    run_type: str,
    as_of_timestamp: str,
) -> Stage1Result:
    as_of_dt = parse_datetime(as_of_timestamp)
    return Stage1Result(
        run_id=run_id,
        run_type=RunType(run_type),
        as_of_timestamp=as_of_dt,
        channel_states=[
            ChannelState(channel=channel, state=0, effective_at=as_of_dt)
            for channel in ("G", "IC", "FC", "ED", "FX")
        ],
        industry_scores=[
            IndustryScore(
                industry_code="IND",
                industry_name="Industry",
                base_score=1.0,
                overlay_adjustment=0.0,
                final_score=1.0,
                rank=1,
            )
        ],
        config_version="sector-v2",
    )


def test_build_manual_context_generates_unique_ids_for_same_published_at() -> None:
    first = build_manual_context(published_at="2026-03-26T12:00:00+09:00")
    second = build_manual_context(published_at="2026-03-26T12:00:00+09:00")

    assert first["run_id"] != second["run_id"]
    assert first["run_id"].startswith("manual-20260326T120000+0900-")
    assert second["run_id"].startswith("manual-20260326T120000+0900-")


def test_build_manual_context_preserves_explicit_run_id() -> None:
    context = build_manual_context(
        run_id="manual-explicit",
        published_at="2026-03-26T12:00:00+09:00",
    )

    assert context["run_id"] == "manual-explicit"


def test_run_manual_cleans_partial_snapshot_before_retry(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "macro_screener.pipeline.runner.bootstrap_runtime",
        lambda config, output_root: _BootstrapStub(store=_StoreStub()),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._load_stage1_rows_and_rank_tables",
        lambda config: (
            [{"industry_code": "IND", "industry_name": "Industry", "exposures": {}}],
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._load_krx_stock_universe",
        lambda **kwargs: KRXLoadResult(
            rows=[{"stock_code": "000001", "stock_name": "Sample", "industry_code": "IND"}],
            source="stub",
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._load_disclosures",
        lambda **kwargs: DARTLoadResult(disclosures=[], warnings=[], watermark=None, source="stub"),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._compute_stage1_result_compat",
        lambda **kwargs: _stage1_result(
            kwargs["context"]["run_id"],
            kwargs["context"]["run_type"],
            kwargs["context"]["as_of_timestamp"],
        ),
    )

    attempts = {"count": 0}

    def flaky_publish(
        snapshot: Any,
        output_root: Path,
        *,
        config: Any,
        store: Any,
        scheduled_window_key: str | None = None,
    ) -> dict[str, str]:
        snapshot_root = (
            config.paths.resolve(config.paths.snapshot_dir, output_root) / snapshot.run_id
        )
        attempts["count"] += 1
        if attempts["count"] == 1:
            snapshot_root.mkdir(parents=True, exist_ok=False)
            raise RuntimeError("synthetic publish failure")
        assert not snapshot_root.exists()
        snapshot_root.mkdir(parents=True, exist_ok=False)
        snapshot_json = snapshot_root / "snapshot.json"
        snapshot_json.write_text("{}", encoding="utf-8")
        return {
            "snapshot_json": str(snapshot_json),
            "status": SnapshotStatus.PUBLISHED.value,
        }

    monkeypatch.setattr("macro_screener.pipeline.runner.publish_snapshot", flaky_publish)

    config_path = tmp_path / "degraded.yaml"
    config_path.write_text("runtime:\n  normal_mode: degraded\n", encoding="utf-8")

    result = run_manual(
        tmp_path,
        published_at="2026-03-26T12:00:00+09:00",
        channel_states={"G": 0, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
        macro_source="manual",
        config_path=config_path,
    )

    assert attempts["count"] == 2
    assert Path(result["latest"]["snapshot_json"]).exists()
