from __future__ import annotations

from datetime import datetime
from typing import Any

from macro_screener.contracts import IndustryScore, Stage1Result
from macro_screener.stage1.base_score import sum_contributions
from macro_screener.stage1.overlay import resolve_overlay_adjustments

DEFAULT_CONFIG_VERSION = "mvp-1"
DEFAULT_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_RUN_TYPE = "manual"
DEFAULT_AS_OF = "2026-03-21T08:30:00+09:00"


def compute_stage1_result(
    *,
    channel_states: dict[str, int],
    exposures: list[dict[str, Any]],
    overlay_adjustments: dict[str, float] | None = None,
    run_id: str = DEFAULT_RUN_ID,
    run_type: str = DEFAULT_RUN_TYPE,
    as_of_timestamp: str | datetime = DEFAULT_AS_OF,
    config_version: str = DEFAULT_CONFIG_VERSION,
) -> Stage1Result:
    overlay_map = resolve_overlay_adjustments(overlay_adjustments)
    missing_channels = [
        channel for channel in ("G", "IC", "FC", "ED", "FX") if channel not in channel_states
    ]
    if missing_channels:
        raise ValueError(f"missing channel states: {', '.join(missing_channels)}")
    ranked_rows: list[IndustryScore] = []
    for row in exposures:
        base_score, negative_penalty, positive_contribution = sum_contributions(
            row["exposures"], channel_states
        )
        overlay_adjustment = float(overlay_map.get(row["industry_code"], 0.0))
        ranked_rows.append(
            IndustryScore(
                industry_code=row["industry_code"],
                industry_name=row["industry_name"],
                base_score=round(base_score, 6),
                overlay_adjustment=round(overlay_adjustment, 6),
                final_score=round(base_score + overlay_adjustment, 6),
                negative_penalty=round(negative_penalty, 6),
                positive_contribution=round(positive_contribution, 6),
                rank=0,
            )
        )
    ranked_rows.sort(
        key=lambda score: (
            -score.final_score,
            score.negative_penalty,
            -score.positive_contribution,
            score.industry_code,
        )
    )
    for index, score in enumerate(ranked_rows, start=1):
        score.rank = index
    as_of_text = (
        as_of_timestamp.isoformat() if isinstance(as_of_timestamp, datetime) else as_of_timestamp
    )
    return Stage1Result(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_text,
        channel_states=dict(channel_states),
        industry_scores=ranked_rows,
        config_version=config_version,
        warnings=[],
    )
