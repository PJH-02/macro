from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from macro_screener.serialization import SerializableMixin, parse_date, parse_datetime


class RunType(str, Enum):
    PRE_OPEN = "pre_open"
    POST_CLOSE = "post_close"
    MANUAL = "manual"
    BACKTEST = "backtest"


class RunMode(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    BACKTEST = "backtest"


class SnapshotStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class ScheduledWindowKey(SerializableMixin):
    trading_date: date
    run_type: RunType

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScheduledWindowKey":
        """딕셔너리 payload로 객체를 생성한다."""
        return cls(
            trading_date=parse_date(payload["trading_date"]),
            run_type=RunType(payload["run_type"]),
        )


@dataclass(frozen=True, slots=True)
class ChannelState(SerializableMixin):
    channel: str
    state: int
    effective_at: datetime
    as_of_timestamp: datetime | None = None
    input_cutoff: datetime | None = None
    source_name: str = "manual"
    source_version: str | None = None
    confidence: float | None = None
    fallback_mode: str | None = None
    warning_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """입력값의 유효성을 검증한다."""
        if self.channel not in {"G", "IC", "FC", "ED", "FX"}:
            raise ValueError(f"Unsupported channel: {self.channel}")
        if self.state not in {-1, 0, 1}:
            raise ValueError(f"Channel state must be -1, 0, or 1, got {self.state}")
        if self.as_of_timestamp is None:
            object.__setattr__(self, "as_of_timestamp", self.effective_at)
        if self.input_cutoff is None:
            object.__setattr__(self, "input_cutoff", self.as_of_timestamp)

    @property
    def source(self) -> str:
        """공개용 소스 이름을 반환한다."""
        return self.source_name

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChannelState":
        """딕셔너리 payload로 객체를 생성한다."""
        effective_at_raw = payload.get("effective_at", payload.get("as_of_timestamp"))
        if effective_at_raw is None:
            raise ValueError("ChannelState requires effective_at or as_of_timestamp")
        as_of_timestamp_raw = payload.get("as_of_timestamp", effective_at_raw)
        input_cutoff_raw = payload.get("input_cutoff", as_of_timestamp_raw)
        return cls(
            channel=str(payload["channel"]),
            state=int(payload["state"]),
            effective_at=parse_datetime(effective_at_raw),
            as_of_timestamp=parse_datetime(as_of_timestamp_raw),
            input_cutoff=parse_datetime(input_cutoff_raw),
            source_name=str(payload.get("source_name", payload.get("source", "manual"))),
            source_version=(
                str(payload["source_version"])
                if payload.get("source_version") is not None
                else None
            ),
            confidence=(
                float(payload["confidence"]) if payload.get("confidence") is not None else None
            ),
            fallback_mode=(
                str(payload["fallback_mode"]) if payload.get("fallback_mode") is not None else None
            ),
            warning_flags=[str(item) for item in payload.get("warning_flags", [])],
        )


@dataclass(frozen=True, slots=True)
class IndustryScore(SerializableMixin):
    industry_code: str
    industry_name: str
    base_score: float
    overlay_adjustment: float
    final_score: float
    rank: int
    negative_penalty: float = 0.0
    positive_contribution: float = 0.0
    channel_contributions: dict[str, float] = field(
        default_factory=lambda: {"G": 0.0, "IC": 0.0, "FC": 0.0, "ED": 0.0, "FX": 0.0}
    )

    def tie_breaker_key(self) -> tuple[float, float, str]:
        """tie breaker key을 처리한다."""
        return (abs(self.negative_penalty), -self.positive_contribution, self.industry_code)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IndustryScore":
        """딕셔너리 payload로 객체를 생성한다."""
        return cls(
            industry_code=str(payload["industry_code"]),
            industry_name=str(payload["industry_name"]),
            base_score=float(payload["base_score"]),
            overlay_adjustment=float(payload["overlay_adjustment"]),
            final_score=float(payload["final_score"]),
            rank=int(payload["rank"]),
            negative_penalty=float(payload.get("negative_penalty", 0.0)),
            positive_contribution=float(payload.get("positive_contribution", 0.0)),
            channel_contributions={
                "G": 0.0,
                "IC": 0.0,
                "FC": 0.0,
                "ED": 0.0,
                "FX": 0.0,
                **{
                    str(key): float(value)
                    for key, value in payload.get("channel_contributions", {}).items()
                },
            },
        )


@dataclass(frozen=True, slots=True)
class RunMetadata(SerializableMixin):
    run_id: str
    run_type: RunType
    as_of_timestamp: datetime
    input_cutoff: datetime
    scheduled_window_key: ScheduledWindowKey | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunMetadata":
        """딕셔너리 payload로 객체를 생성한다."""
        window_payload = payload.get("scheduled_window_key")
        return cls(
            run_id=str(payload["run_id"]),
            run_type=RunType(payload["run_type"]),
            as_of_timestamp=parse_datetime(payload["as_of_timestamp"]),
            input_cutoff=parse_datetime(payload["input_cutoff"]),
            scheduled_window_key=(
                ScheduledWindowKey.from_dict(window_payload)
                if isinstance(window_payload, dict)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class Stage1Result(SerializableMixin):
    run_id: str
    run_type: RunType
    as_of_timestamp: datetime
    channel_states: list[ChannelState]
    industry_scores: list[IndustryScore]
    config_version: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Stage1Result":
        """딕셔너리 payload로 객체를 생성한다."""
        return cls(
            run_id=str(payload["run_id"]),
            run_type=RunType(payload["run_type"]),
            as_of_timestamp=parse_datetime(payload["as_of_timestamp"]),
            channel_states=[
                ChannelState.from_dict(item) for item in payload.get("channel_states", [])
            ],
            industry_scores=[
                IndustryScore.from_dict(item) for item in payload.get("industry_scores", [])
            ],
            config_version=str(payload["config_version"]),
            warnings=[str(item) for item in payload.get("warnings", [])],
        )


@dataclass(frozen=True, slots=True)
class CalendarContext(SerializableMixin):
    trading_date: date
    is_trading_day: bool
    previous_trading_date: date | None = None
    next_trading_date: date | None = None
    holiday_calendar_version: str = "mvp-hardcoded"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalendarContext":
        """딕셔너리 payload로 객체를 생성한다."""
        previous = payload.get("previous_trading_date")
        next_value = payload.get("next_trading_date")
        return cls(
            trading_date=parse_date(payload["trading_date"]),
            is_trading_day=bool(payload["is_trading_day"]),
            previous_trading_date=parse_date(previous) if previous is not None else None,
            next_trading_date=parse_date(next_value) if next_value is not None else None,
            holiday_calendar_version=str(payload.get("holiday_calendar_version", "mvp-hardcoded")),
        )


@dataclass(frozen=True, slots=True)
class ScoringContext(SerializableMixin):
    run_metadata: RunMetadata
    stage1_result: Stage1Result
    config: dict[str, Any]
    calendar_context: CalendarContext
    mode: RunMode
    input_cutoff: datetime

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScoringContext":
        """딕셔너리 payload로 객체를 생성한다."""
        config_payload = payload.get("config", {})
        if not isinstance(config_payload, dict):
            raise ValueError("ScoringContext config must be a mapping")
        return cls(
            run_metadata=RunMetadata.from_dict(payload["run_metadata"]),
            stage1_result=Stage1Result.from_dict(payload["stage1_result"]),
            config=config_payload,
            calendar_context=CalendarContext.from_dict(payload["calendar_context"]),
            mode=RunMode(payload["mode"]),
            input_cutoff=parse_datetime(payload["input_cutoff"]),
        )


@dataclass(frozen=True, slots=True)
class StockScore(SerializableMixin):
    stock_code: str
    stock_name: str
    industry_code: str
    final_score: float
    rank: int
    raw_dart_score: float
    raw_industry_score: float
    normalized_dart_score: float
    normalized_industry_score: float
    normalized_financial_score: float = 0.0
    block_scores: dict[str, float] = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)

    def tie_breaker_key(self) -> tuple[float, float, str]:
        """tie breaker key을 처리한다."""
        return (-self.raw_dart_score, -self.raw_industry_score, self.stock_code)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StockScore":
        """딕셔너리 payload로 객체를 생성한다."""
        return cls(
            stock_code=str(payload["stock_code"]),
            stock_name=str(payload["stock_name"]),
            industry_code=str(payload["industry_code"]),
            final_score=float(payload["final_score"]),
            rank=int(payload["rank"]),
            raw_dart_score=float(payload["raw_dart_score"]),
            raw_industry_score=float(payload["raw_industry_score"]),
            normalized_dart_score=float(payload["normalized_dart_score"]),
            normalized_industry_score=float(payload["normalized_industry_score"]),
            normalized_financial_score=float(payload.get("normalized_financial_score", 0.0)),
            block_scores={
                str(key): float(value) for key, value in payload.get("block_scores", {}).items()
            },
            risk_flags=[str(item) for item in payload.get("risk_flags", [])],
        )


@dataclass(frozen=True, slots=True)
class Snapshot(SerializableMixin):
    run_id: str
    run_type: RunType
    as_of_timestamp: datetime
    input_cutoff: datetime
    published_at: datetime | None
    status: SnapshotStatus
    industry_scores: list[IndustryScore]
    stock_scores: list[StockScore]
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Snapshot":
        """딕셔너리 payload로 객체를 생성한다."""
        published = payload.get("published_at")
        return cls(
            run_id=str(payload["run_id"]),
            run_type=RunType(payload["run_type"]),
            as_of_timestamp=parse_datetime(payload["as_of_timestamp"]),
            input_cutoff=parse_datetime(payload["input_cutoff"]),
            published_at=parse_datetime(published) if published is not None else None,
            status=SnapshotStatus(payload["status"]),
            industry_scores=[
                IndustryScore.from_dict(item) for item in payload.get("industry_scores", [])
            ],
            stock_scores=[StockScore.from_dict(item) for item in payload.get("stock_scores", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
        )
