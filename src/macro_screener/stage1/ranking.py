from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from macro_screener.models import IndustryScore, RunType, Stage1Result
from macro_screener.serialization import parse_datetime
from macro_screener.stage1.base_score import (
    channel_contribution_map,
    rank_to_score,
    sum_contributions,
    summarize_weighted_contributions,
)
from macro_screener.stage1.channel_state import build_channel_state_records
from macro_screener.stage1.overlay import resolve_overlay_adjustments

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
REGIME_KEY_BY_STATE: dict[int, str] = {1: "pos", -1: "neg"}
DEFAULT_CONFIG_VERSION = "mvp-1"
DEFAULT_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_RUN_TYPE = RunType.MANUAL.value
DEFAULT_AS_OF = "2026-03-21T08:30:00+09:00"


def load_stage1_artifact(path: str | Path) -> dict[str, Any]:
    """stage1 산출물을 불러온다"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stage1 artifact must be a mapping")
    return payload


def _build_rank_lookup(
    sector_rank_tables: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, dict[str, int]]]:
    """순위 lookup을 구성한다"""
    lookup: dict[str, dict[str, dict[str, int]]] = {}
    for channel in CHANNELS:
        channel_tables = sector_rank_tables.get(channel)
        if channel_tables is None:
            raise ValueError(f"missing sector rank tables for channel {channel}")
        lookup[channel] = {}
        for regime in ("pos", "neg"):
            ordered = channel_tables.get(regime)
            if ordered is None:
                raise ValueError(f"missing {regime} sector rank table for channel {channel}")
            lookup[channel][regime] = {
                industry_code: rank for rank, industry_code in enumerate(ordered, start=1)
            }
    return lookup


def _weighted_ranked_contributions(
    *,
    industry_code: str,
    channel_states: dict[str, int],
    rank_lookup: dict[str, dict[str, dict[str, int]]],
    channel_weights: dict[str, float],
) -> dict[str, float]:
    """가중 ranked 기여도을 처리한다."""
    weighted: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
    for channel in CHANNELS:
        state = channel_states[channel]
        if state == 0:
            continue
        regime = REGIME_KEY_BY_STATE[state]
        channel_ranks = rank_lookup[channel][regime]
        rank = channel_ranks.get(industry_code)
        if rank is None:
            raise ValueError(
                f"industry {industry_code} missing from {channel}/{regime} rank table"
            )
        total = len(channel_ranks)
        weighted[channel] = round(channel_weights[channel] * rank_to_score(rank, total), 6)
    return weighted


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
    """1단계 점수 결과를 계산한다."""
    overlay_map = resolve_overlay_adjustments(overlay_adjustments)
    missing_channels = [
        channel for channel in CHANNELS if channel not in channel_states
    ]
    if missing_channels:
        raise ValueError(f"missing channel states: {', '.join(missing_channels)}")
    if sector_rank_tables is not None:
        resolved_weights = channel_weights or {channel: 1.0 for channel in CHANNELS}
        missing_weights = [channel for channel in CHANNELS if channel not in resolved_weights]
        if missing_weights:
            raise ValueError(f"missing channel weights: {', '.join(missing_weights)}")
        rank_lookup = _build_rank_lookup(sector_rank_tables)

    run_type_value = run_type if isinstance(run_type, RunType) else RunType(str(run_type))
    as_of_dt = parse_datetime(as_of_timestamp)
    cutoff_dt = parse_datetime(input_cutoff) if input_cutoff is not None else as_of_dt
    ranked_rows: list[dict[str, Any]] = []
    for row in exposures:
        if sector_rank_tables is None:
            contributions = channel_contribution_map(row["exposures"], channel_states)
            base_score, negative_penalty, positive_contribution = sum_contributions(
                row["exposures"], channel_states
            )
        else:
            contributions = _weighted_ranked_contributions(
                industry_code=str(row["industry_code"]),
                channel_states=channel_states,
                rank_lookup=rank_lookup,
                channel_weights=resolved_weights,
            )
            base_score, negative_penalty, positive_contribution = summarize_weighted_contributions(
                contributions
            )
        overlay_adjustment = float(overlay_map.get(row["industry_code"], 0.0))
        ranked_rows.append(
            {
                "industry_code": row["industry_code"],
                "industry_name": row["industry_name"],
                "base_score": round(base_score, 6),
                "overlay_adjustment": round(overlay_adjustment, 6),
                "final_score": round(base_score + overlay_adjustment, 6),
                "negative_penalty": round(negative_penalty, 6),
                "positive_contribution": round(positive_contribution, 6),
                "channel_contributions": {
                    channel: round(value, 6) for channel, value in contributions.items()
                },
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
    )
