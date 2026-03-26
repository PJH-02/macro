from __future__ import annotations

from datetime import datetime
from typing import Any

from macro_screener.models import IndustryScore, RunType, Stage1Result
from macro_screener.serialization import parse_datetime
from macro_screener.stage1.channel_state import build_channel_state_records
from macro_screener.stage1.overlay import resolve_overlay_adjustments

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
DEFAULT_CONFIG_VERSION = "sector-v2"
DEFAULT_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_RUN_TYPE = RunType.MANUAL.value
DEFAULT_AS_OF = "2026-03-21T08:30:00+09:00"


def _channel_score_map(channel_states: dict[str, int]) -> dict[str, dict[str, float]]:
    return {
        channel: {
            "lt_score": float(channel_states.get(channel, 0)),
            "overlay_score": 0.0,
            "total_score": float(channel_states.get(channel, 0)),
            "indicator_details": [],
            "warnings": [],
        }
        for channel in CHANNELS
    }


def compute_stage1_result(
    *,
    channel_states: dict[str, int],
    exposures: list[dict[str, Any]],
    overlay_adjustments: dict[str, float] | None = None,
    run_id: str = DEFAULT_RUN_ID,
    run_type: str | RunType = DEFAULT_RUN_TYPE,
    as_of_timestamp: str | datetime = DEFAULT_AS_OF,
    input_cutoff: str | datetime | None = None,
    config_version: str = DEFAULT_CONFIG_VERSION,
    channel_state_source: str = "manual",
    channel_state_source_version: str | None = None,
    channel_state_confidence: dict[str, float] | None = None,
    channel_state_fallback_mode: str | None = None,
    channel_state_warning_flags: dict[str, list[str]] | None = None,
    sector_rank_tables: dict[str, dict[str, list[str]]] | None = None,
    channel_weights: dict[str, float] | None = None,
) -> Stage1Result:
    """Compute grouped-sector scores via direct channel-score × exposure multiplication."""
    _ = sector_rank_tables, channel_weights  # retained for compatibility at call sites
    overlay_map = resolve_overlay_adjustments(overlay_adjustments)
    missing_channels = [channel for channel in CHANNELS if channel not in channel_states]
    if missing_channels:
        raise ValueError(f"missing channel states: {', '.join(missing_channels)}")

    run_type_value = run_type if isinstance(run_type, RunType) else RunType(str(run_type))
    as_of_dt = parse_datetime(as_of_timestamp)
    cutoff_dt = parse_datetime(input_cutoff) if input_cutoff is not None else as_of_dt
    channel_scores = _channel_score_map(channel_states)

    ranked_rows: list[dict[str, Any]] = []
    for row in exposures:
        contributions = {
            channel: round(float(channel_scores[channel]["total_score"]) * float(row["exposures"].get(channel, 0.0)), 6)
            for channel in CHANNELS
        }
        base_score = round(sum(contributions.values()), 6)
        overlay_adjustment = round(float(overlay_map.get(row["industry_code"], 0.0)), 6)
        positive_contribution = round(sum(value for value in contributions.values() if value > 0), 6)
        negative_penalty = round(abs(sum(value for value in contributions.values() if value < 0)), 6)
        ranked_rows.append(
            {
                "industry_code": row["industry_code"],
                "industry_name": row["industry_name"],
                "base_score": base_score,
                "overlay_adjustment": overlay_adjustment,
                "final_score": round(base_score + overlay_adjustment, 6),
                "negative_penalty": negative_penalty,
                "positive_contribution": positive_contribution,
                "channel_contributions": contributions,
            }
        )

    ranked_rows.sort(
        key=lambda score: (
            -score["final_score"],
            score["negative_penalty"],
            -score["positive_contribution"],
            score["industry_code"],
        )
    )
    industry_scores = [
        IndustryScore(
            industry_code=row["industry_code"],
            industry_name=row["industry_name"],
            base_score=row["base_score"],
            overlay_adjustment=row["overlay_adjustment"],
            final_score=row["final_score"],
            rank=index,
            negative_penalty=row["negative_penalty"],
            positive_contribution=row["positive_contribution"],
            channel_contributions=row["channel_contributions"],
        )
        for index, row in enumerate(ranked_rows, start=1)
    ]
    return Stage1Result(
        run_id=run_id,
        run_type=run_type_value,
        as_of_timestamp=as_of_dt,
        channel_states=build_channel_state_records(
            channel_states,
            effective_at=as_of_dt,
            as_of_timestamp=as_of_dt,
            input_cutoff=cutoff_dt,
            source_name=channel_state_source,
            source_version=channel_state_source_version,
            confidence_by_channel=channel_state_confidence,
            fallback_mode=channel_state_fallback_mode,
            warning_flags_by_channel=channel_state_warning_flags,
        ),
        industry_scores=industry_scores,
        config_version=config_version,
        warnings=[],
        channel_scores=channel_scores,
    )
