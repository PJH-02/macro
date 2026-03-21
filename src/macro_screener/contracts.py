from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class IndustryScore:
    industry_code: str
    industry_name: str
    base_score: float
    overlay_adjustment: float
    final_score: float
    negative_penalty: float
    positive_contribution: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Stage1Result:
    run_id: str
    run_type: str
    as_of_timestamp: str
    channel_states: dict[str, int]
    industry_scores: list[IndustryScore]
    config_version: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["industry_scores"] = [score.to_dict() for score in self.industry_scores]
        return payload


@dataclass(slots=True)
class StockScore:
    stock_code: str
    stock_name: str
    industry_code: str
    final_score: float
    rank: int
    raw_dart_score: float
    raw_industry_score: float
    normalized_dart_score: float
    normalized_industry_score: float
    normalized_financial_score: float
    risk_flags: list[str]
    block_breakdown: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Snapshot:
    run_id: str
    run_type: str
    as_of_timestamp: str
    input_cutoff: str
    published_at: str
    status: str
    industry_scores: list[IndustryScore]
    stock_scores: list[StockScore]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["industry_scores"] = [score.to_dict() for score in self.industry_scores]
        payload["stock_scores"] = [score.to_dict() for score in self.stock_scores]
        return payload
