from __future__ import annotations

from pathlib import Path
from typing import Any

from macro_screener.contracts import Snapshot
from macro_screener.data.dart_client import DARTClient
from macro_screener.data.krx_client import KRXClient
from macro_screener.data.macro_client import DEFAULT_CHANNEL_STATES, ManualMacroDataSource
from macro_screener.pipeline.publisher import publish_snapshot
from macro_screener.pipeline.scheduler import build_scheduled_context
from macro_screener.stage1.overlay import DEFAULT_OVERLAYS
from macro_screener.stage1.ranking import compute_stage1_result
from macro_screener.stage2.ranking import compute_stock_scores

DEFAULT_DEMO_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_DEMO_RUN_TYPE = "manual"
DEFAULT_DEMO_AS_OF = "2026-03-21T08:30:00+09:00"
DEFAULT_DEMO_INPUT_CUTOFF = "2026-03-20T18:00:00+09:00"
DEFAULT_CONFIG_VERSION = "mvp-1"


def build_demo_snapshot(
    *,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    input_cutoff: str = DEFAULT_DEMO_INPUT_CUTOFF,
    published_at: str = DEFAULT_DEMO_AS_OF,
    channel_states: dict[str, int] | None = None,
) -> Snapshot:
    macro_source = ManualMacroDataSource(channel_states or DEFAULT_CHANNEL_STATES)
    krx_client = KRXClient(stock_classification_path=Path("stock_classification.csv"))
    dart_client = DARTClient()
    stage1_result = compute_stage1_result(
        channel_states=macro_source.fetch_channel_states(),
        exposures=krx_client.load_demo_exposures(),
        overlay_adjustments=DEFAULT_OVERLAYS,
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        config_version=DEFAULT_CONFIG_VERSION,
    )
    stock_scores, stage2_warnings = compute_stock_scores(
        stage1_result=stage1_result,
        stocks=krx_client.load_demo_stocks(),
        disclosures=dart_client.load_demo_disclosures(),
    )
    return Snapshot(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        published_at=published_at,
        status="published",
        industry_scores=stage1_result.industry_scores,
        stock_scores=stock_scores,
        warnings=[*stage1_result.warnings, *stage2_warnings],
    )


def run_demo(
    output_dir: str | Path,
    *,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    input_cutoff: str = DEFAULT_DEMO_INPUT_CUTOFF,
    published_at: str = DEFAULT_DEMO_AS_OF,
) -> dict[str, Any]:
    snapshot = build_demo_snapshot(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        published_at=published_at,
    )
    latest_payload = publish_snapshot(snapshot, output_dir)
    return {"snapshot": snapshot.to_dict(), "latest": latest_payload}


def run_scheduled_stub(
    output_dir: str | Path,
    *,
    trading_date: str,
    run_type: str,
) -> dict[str, Any]:
    context = build_scheduled_context(trading_date, run_type)
    result = run_demo(
        output_dir,
        run_id=context["run_id"],
        run_type=context["run_type"],
        as_of_timestamp=context["as_of_timestamp"],
        input_cutoff=context["input_cutoff"],
        published_at=context["published_at"],
    )
    return {"context": context, **result}
