from __future__ import annotations

from collections import defaultdict
from typing import Any

from macro_screener.contracts import StockScore
from macro_screener.stage2.classifier import classify_disclosure
from macro_screener.stage2.decay import decayed_score
from macro_screener.stage2.normalize import zscore

DEFAULT_LAMBDA = 0.35


def compute_stock_scores(
    *,
    stage1_result: Any,
    stocks: list[dict[str, Any]],
    disclosures: list[dict[str, Any]],
    lambda_weight: float = DEFAULT_LAMBDA,
) -> tuple[list[StockScore], list[str]]:
    industry_score_map = {
        score.industry_code: score.final_score for score in stage1_result.industry_scores
    }
    grouped_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown_count = 0
    total_events = 0
    for disclosure in disclosures:
        total_events += 1
        block_name = classify_disclosure(disclosure.get("event_code"), disclosure.get("title", ""))
        if block_name == "neutral":
            unknown_count += 1
        grouped_events[disclosure["stock_code"]].append({**disclosure, "block_name": block_name})

    stock_rows: list[dict[str, Any]] = []
    for stock in stocks:
        block_breakdown: dict[str, float] = defaultdict(float)
        risk_flags: set[str] = set()
        raw_dart_score = 0.0
        for event in grouped_events.get(stock["stock_code"], []):
            block_name = event["block_name"]
            contribution = decayed_score(block_name, int(event.get("trading_days_elapsed", 0)))
            block_breakdown[block_name] += contribution
            raw_dart_score += contribution
            if block_name in {
                "dilutive_financing",
                "correction_cancellation_withdrawal",
                "governance_risk",
            }:
                risk_flags.add(block_name)
        stock_rows.append(
            {
                "stock_code": stock["stock_code"],
                "stock_name": stock["stock_name"],
                "industry_code": stock["industry_code"],
                "raw_dart_score": round(raw_dart_score, 6),
                "raw_industry_score": round(float(industry_score_map[stock["industry_code"]]), 6),
                "risk_flags": sorted(risk_flags),
                "block_breakdown": {
                    key: round(value, 6) for key, value in sorted(block_breakdown.items())
                },
            }
        )

    dart_scores = [row["raw_dart_score"] for row in stock_rows]
    industry_scores = [row["raw_industry_score"] for row in stock_rows]
    normalized_dart_scores = zscore(dart_scores)
    normalized_industry_scores = zscore(industry_scores)

    stock_scores: list[StockScore] = []
    for row, normalized_dart, normalized_industry in zip(
        stock_rows, normalized_dart_scores, normalized_industry_scores, strict=True
    ):
        final_score = round(normalized_dart + lambda_weight * normalized_industry, 6)
        stock_scores.append(
            StockScore(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                industry_code=row["industry_code"],
                final_score=final_score,
                rank=0,
                raw_dart_score=row["raw_dart_score"],
                raw_industry_score=row["raw_industry_score"],
                normalized_dart_score=normalized_dart,
                normalized_industry_score=normalized_industry,
                normalized_financial_score=0.0,
                risk_flags=row["risk_flags"],
                block_breakdown=row["block_breakdown"],
            )
        )
    stock_scores.sort(
        key=lambda score: (
            -score.final_score,
            -score.raw_dart_score,
            -score.raw_industry_score,
            score.stock_code,
        )
    )
    for index, score in enumerate(stock_scores, start=1):
        score.rank = index
    warnings: list[str] = []
    if total_events and (unknown_count / total_events) > 0.2:
        warnings.append(
            f"unknown_dart_classification_ratio={unknown_count / total_events:.2%} exceeds 20%"
        )
    return stock_scores, warnings
