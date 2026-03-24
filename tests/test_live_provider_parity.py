from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from macro_screener.data.dart_client import DARTLoadResult
from macro_screener.data.krx_client import KRXLoadResult
from macro_screener.data.macro_client import MacroLoadResult
from macro_screener.models import ChannelState, IndustryScore, RunType, SnapshotStatus, Stage1Result
from macro_screener.pipeline.runner import run_manual, run_scheduled
from macro_screener.serialization import parse_datetime
from macro_screener.stage2.ranking import compute_stock_scores


@dataclass
class _StoreStub:
    saved_sources: list[str]

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
        if source is not None:
            self.saved_sources.append(source)


@dataclass
class _BootstrapStub:
    store: _StoreStub


class _MacroSourceStub:
    def fetch_channel_states(self) -> MacroLoadResult:
        return MacroLoadResult(
            channel_states={"G": 1, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
            source_name="ecos_kosis_fred_live",
        )


def _stage1_result(
    run_id: str,
    run_type: str,
    as_of_timestamp: str,
    *,
    g_state: int = 1,
    final_score: float = 1.0,
) -> Stage1Result:
    as_of_dt = parse_datetime(as_of_timestamp)
    return Stage1Result(
        run_id=run_id,
        run_type=RunType(run_type),
        as_of_timestamp=as_of_dt,
        channel_states=[
            ChannelState(
                channel=channel,
                state=0 if channel != "G" else g_state,
                effective_at=as_of_dt,
            )
            for channel in ("G", "IC", "FC", "ED", "FX")
        ],
        industry_scores=[
            IndustryScore(
                industry_code="IND",
                industry_name="Industry",
                base_score=final_score,
                overlay_adjustment=0.0,
                final_score=final_score,
                rank=1,
                channel_contributions={
                    "G": final_score,
                    "IC": 0.0,
                    "FC": 0.0,
                    "ED": 0.0,
                    "FX": 0.0,
                },
            )
        ],
        config_version="mvp-1",
    )


def test_manual_and_scheduled_runs_share_live_provider_path(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    saved_sources: list[str] = []

    monkeypatch.setattr(
        "macro_screener.pipeline.runner.bootstrap_runtime",
        lambda config, output_root: _BootstrapStub(store=_StoreStub(saved_sources)),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner.load_live_macro_data_source",
        lambda **kwargs: _MacroSourceStub(),
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
            source="live",
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._load_disclosures",
        lambda **kwargs: DARTLoadResult(
            disclosures=[
                {
                    "stock_code": "000001",
                    "event_code": "B01",
                    "title": "공급계약",
                    "trading_days_elapsed": 0,
                }
            ],
            warnings=[],
            watermark="2026-03-24T08:30:00+09:00",
            source="live",
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._compute_stage1_result_compat",
        lambda **kwargs: _stage1_result(
            kwargs["context"]["run_id"],
            kwargs["context"]["run_type"],
            kwargs["context"]["as_of_timestamp"],
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner.publish_snapshot",
        lambda snapshot, output_root, config, store, scheduled_window_key=None: {
            "snapshot_json": str(output_root / "snapshot.json"),
            "status": SnapshotStatus.PUBLISHED.value,
        },
    )

    manual = run_manual(
        tmp_path / "manual",
        run_id="manual-parity",
        run_type="pre_open",
        as_of_timestamp="2026-03-24T08:30:00+09:00",
        input_cutoff="2026-03-23T18:00:00+09:00",
        published_at="2026-03-24T08:30:00+09:00",
        macro_source="live",
    )
    scheduled = run_scheduled(
        tmp_path / "scheduled",
        trading_date="2026-03-24",
        run_type="pre_open",
        attempted_at="2026-03-24T08:30:00+09:00",
        macro_source="live",
    )

    assert saved_sources == ["ecos_kosis_fred_live", "ecos_kosis_fred_live"]
    assert manual["snapshot"]["industry_scores"] == scheduled["snapshot"]["industry_scores"]
    assert manual["snapshot"]["stock_scores"] == scheduled["snapshot"]["stock_scores"]
    assert manual["warnings"] == scheduled["warnings"]


def test_explicit_manual_macro_source_keeps_manual_defaults(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    saved_sources: list[str] = []

    monkeypatch.setattr(
        "macro_screener.pipeline.runner.bootstrap_runtime",
        lambda config, output_root: _BootstrapStub(store=_StoreStub(saved_sources)),
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
        lambda **kwargs: KRXLoadResult(rows=[], source="live", warnings=[]),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._load_disclosures",
        lambda **kwargs: DARTLoadResult(disclosures=[], warnings=[], watermark=None, source="live"),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner._compute_stage1_result_compat",
        lambda **kwargs: _stage1_result(
            kwargs["context"]["run_id"],
            kwargs["context"]["run_type"],
            kwargs["context"]["as_of_timestamp"],
            g_state=0,
            final_score=0.0,
        ),
    )
    monkeypatch.setattr(
        "macro_screener.pipeline.runner.publish_snapshot",
        lambda snapshot, output_root, config, store, scheduled_window_key=None: {
            "snapshot_json": str(output_root / "snapshot.json"),
            "status": SnapshotStatus.PUBLISHED.value,
        },
    )

    result = run_manual(
        tmp_path / "manual-fallback",
        run_id="manual-fallback",
        published_at="2026-03-24T08:30:00+09:00",
        macro_source="manual",
    )

    assert saved_sources == ["manual_config"]
    assert result["snapshot"]["industry_scores"][0]["final_score"] == 0.0


def test_live_macro_data_source_wires_optional_kosis(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "macro_screener.data.macro_client._require_api_key",
        lambda env_name: f"{env_name}-token",
    )
    monkeypatch.setattr(
        "macro_screener.data.macro_client._load_ecos_runtime_payloads",
        lambda **kwargs: {"kr_ipi_yoy_3mma": {"provider": "ecos", "series": [{"value": "1.0"}]}},
    )
    monkeypatch.setattr(
        "macro_screener.data.macro_client._load_kosis_runtime_payloads",
        lambda **kwargs: (
            {"kr_exports_us_yoy_3mma": {"provider": "kosis", "series": [{"value": "2.0"}]}},
            {},
            {},
            False,
        ),
    )
    monkeypatch.setattr(
        "macro_screener.data.macro_client._load_fred_runtime_payloads",
        lambda **kwargs: (
            {"us_ipi_yoy_3mma": {"provider": "us_macro", "series": [{"value": "1.0"}]}},
            {},
            {},
            False,
        ),
    )
    monkeypatch.setattr(
        "macro_screener.data.macro_client.build_live_macro_data_source_from_provider_payloads",
        lambda series_payloads, **kwargs: captured.update(
            {"series_payloads": series_payloads, "kwargs": kwargs}
        ),
    )

    from macro_screener.data import macro_client

    macro_client.load_live_macro_data_source(
        as_of_timestamp="2026-03-24T08:30:00+09:00",
        input_cutoff="2026-03-23T18:00:00+09:00",
        kosis_exports_us_user_stats_id="USER_STATS_ID",
    )

    assert captured["series_payloads"]["kr_exports_us_yoy_3mma"]["provider"] == "kosis"
    assert captured["kwargs"]["degraded_mode"] is False


def test_generic_business_reports_are_ignored_in_stage2() -> None:
    stage1_result = _stage1_result(
        "manual-generic",
        RunType.MANUAL.value,
        "2026-03-24T08:30:00+09:00",
    )
    stock_scores, warnings = compute_stock_scores(
        stage1_result=stage1_result,
        stocks=[{"stock_code": "000001", "stock_name": "Sample", "industry_code": "IND"}],
        disclosures=[
            {
                "stock_code": "000001",
                "event_code": None,
                "title": "[첨부추가]사업보고서 (2025.12)",
                "trading_days_elapsed": 0,
            }
        ],
    )

    assert warnings == []
    assert stock_scores[0].raw_dart_score == 0.0
