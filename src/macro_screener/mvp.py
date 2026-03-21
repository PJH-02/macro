from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .contracts import IndustryScore, Snapshot, Stage1Result, StockScore

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
DEFAULT_DEMO_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_DEMO_RUN_TYPE = "manual"
DEFAULT_DEMO_AS_OF = "2026-03-21T08:30:00+09:00"
DEFAULT_DEMO_INPUT_CUTOFF = "2026-03-20T18:00:00+09:00"
DEFAULT_CONFIG_VERSION = "mvp-1"
DEFAULT_LAMBDA = 0.35
DEFAULT_BACKTEST_RUN_TYPE = "post_close"
MVP_HOLIDAYS = frozenset({"2026-01-01"})
SCHEDULED_RUN_TIMES = {
    "pre_open": "08:30:00+09:00",
    "post_close": "15:45:00+09:00",
}


def _is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day.isoformat() not in MVP_HOLIDAYS


def _previous_trading_day(day: date) -> date:
    previous = day - timedelta(days=1)
    while not _is_trading_day(previous):
        previous -= timedelta(days=1)
    return previous

BLOCK_WEIGHTS = {
    "supply_contract": 1.0,
    "treasury_stock": 0.8,
    "facility_investment": 0.6,
    "dilutive_financing": -1.0,
    "correction_cancellation_withdrawal": -0.7,
    "governance_risk": -0.9,
    "neutral": 0.0,
}

HALF_LIVES = {
    "supply_contract": 20,
    "treasury_stock": 10,
    "facility_investment": 60,
    "dilutive_financing": 60,
    "correction_cancellation_withdrawal": 10,
    "governance_risk": 120,
}

EVENT_CODE_MAP = {
    "B01": "supply_contract",
    "B02": "treasury_stock",
    "B03": "facility_investment",
    "N01": "dilutive_financing",
    "N02": "correction_cancellation_withdrawal",
    "N03": "governance_risk",
}

TITLE_PATTERNS = (
    ("supply_contract", ("공급계약", "판매계약")),
    ("treasury_stock", ("자기주식", "자사주")),
    ("facility_investment", ("시설투자", "생산설비")),
    ("dilutive_financing", ("유상증자", "전환사채", "교환사채", "신주인수권부사채")),
    ("correction_cancellation_withdrawal", ("정정", "취소", "철회")),
    ("governance_risk", ("횡령", "배임", "불성실공시")),
)


def _sum_contributions(
    exposures: dict[str, int], channel_states: dict[str, int]
) -> tuple[float, float, float]:
    base_score = 0.0
    negative_penalty = 0.0
    positive_contribution = 0.0
    for channel in CHANNELS:
        contribution = float(exposures.get(channel, 0) * channel_states.get(channel, 0))
        base_score += contribution
        if contribution < 0:
            negative_penalty += abs(contribution)
        elif contribution > 0:
            positive_contribution += contribution
    return base_score, negative_penalty, positive_contribution


def compute_stage1_result(
    *,
    channel_states: dict[str, int],
    exposures: Iterable[dict[str, Any]],
    overlay_adjustments: dict[str, float] | None = None,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    config_version: str = DEFAULT_CONFIG_VERSION,
) -> Stage1Result:
    overlay_adjustments = overlay_adjustments or {}
    missing_channels = [channel for channel in CHANNELS if channel not in channel_states]
    if missing_channels:
        raise ValueError(f"missing channel states: {', '.join(missing_channels)}")

    ranked_rows: list[IndustryScore] = []
    for row in exposures:
        base_score, negative_penalty, positive_contribution = _sum_contributions(
            row["exposures"], channel_states
        )
        overlay_adjustment = float(overlay_adjustments.get(row["industry_code"], 0.0))
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

    return Stage1Result(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        channel_states=channel_states,
        industry_scores=ranked_rows,
        config_version=config_version,
        warnings=[],
    )


def classify_disclosure(event_code: str | None, title: str) -> str:
    if event_code and event_code in EVENT_CODE_MAP:
        return EVENT_CODE_MAP[event_code]

    normalized_title = title.strip().lower()
    for block_name, patterns in TITLE_PATTERNS:
        if any(pattern.lower() in normalized_title for pattern in patterns):
            return block_name
    return "neutral"


def _decayed_score(block_name: str, trading_days_elapsed: int) -> float:
    weight = BLOCK_WEIGHTS[block_name]
    if weight == 0.0:
        return 0.0
    half_life = HALF_LIVES[block_name]
    decay = math.exp(-math.log(2) * max(trading_days_elapsed, 0) / half_life)
    return weight * decay


def _zscore(values: list[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    if variance == 0.0:
        return [0.0 for _ in values]
    stddev = math.sqrt(variance)
    return [round((value - mean) / stddev, 6) for value in values]


def compute_stock_scores(
    *,
    stage1_result: Stage1Result,
    stocks: Iterable[dict[str, Any]],
    disclosures: Iterable[dict[str, Any]],
    lambda_weight: float = DEFAULT_LAMBDA,
) -> tuple[list[StockScore], list[str]]:
    industry_score_map = {
        score.industry_code: score.final_score
        for score in stage1_result.industry_scores
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
            contribution = _decayed_score(block_name, int(event.get("trading_days_elapsed", 0)))
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
                    key: round(value, 6)
                    for key, value in sorted(block_breakdown.items())
                },
            }
        )

    dart_scores = [row["raw_dart_score"] for row in stock_rows]
    industry_scores = [row["raw_industry_score"] for row in stock_rows]
    normalized_dart_scores = _zscore(dart_scores)
    normalized_industry_scores = _zscore(industry_scores)

    stock_scores: list[StockScore] = []
    for row, normalized_dart, normalized_industry in zip(
        stock_rows,
        normalized_dart_scores,
        normalized_industry_scores,
        strict=True,
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


_DEMO_EXPOSURES = [
    {
        "industry_code": "AUTO",
        "industry_name": "Automobiles",
        "exposures": {"G": 1, "IC": -1, "FC": -1, "ED": 1, "FX": 0},
    },
    {
        "industry_code": "SHIP",
        "industry_name": "Shipbuilding",
        "exposures": {"G": 1, "IC": -1, "FC": 0, "ED": 1, "FX": 1},
    },
    {
        "industry_code": "PHARMA",
        "industry_name": "Pharmaceuticals",
        "exposures": {"G": 0, "IC": -1, "FC": 0, "ED": 0, "FX": -1},
    },
]

_DEMO_OVERLAYS = {"AUTO": 0.2, "SHIP": 0.1, "PHARMA": 0.0}

_DEMO_STOCKS = [
    {"stock_code": "000270", "stock_name": "Kia", "industry_code": "AUTO"},
    {"stock_code": "005380", "stock_name": "Hyundai Motor", "industry_code": "AUTO"},
    {"stock_code": "009540", "stock_name": "HD Korea Shipbuilding", "industry_code": "SHIP"},
    {"stock_code": "000100", "stock_name": "Yuhan", "industry_code": "PHARMA"},
]

_DEMO_DISCLOSURES = [
    {
        "stock_code": "000270",
        "event_code": "B01",
        "title": "대규모 공급계약 체결",
        "trading_days_elapsed": 2,
    },
    {
        "stock_code": "005380",
        "event_code": "N01",
        "title": "유상증자 결정",
        "trading_days_elapsed": 5,
    },
    {
        "stock_code": "009540",
        "event_code": None,
        "title": "시설투자 결정",
        "trading_days_elapsed": 10,
    },
    {"stock_code": "009540", "event_code": None, "title": "정정 공시", "trading_days_elapsed": 1},
    {"stock_code": "000100", "event_code": None, "title": "설명회 개최", "trading_days_elapsed": 0},
]


def build_demo_snapshot(
    *,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    input_cutoff: str = DEFAULT_DEMO_INPUT_CUTOFF,
    published_at: str = DEFAULT_DEMO_AS_OF,
    channel_states: dict[str, int] | None = None,
) -> Snapshot:
    channel_states = channel_states or {"G": 1, "IC": -1, "FC": 0, "ED": 1, "FX": 1}
    stage1_result = compute_stage1_result(
        channel_states=channel_states,
        exposures=_DEMO_EXPOSURES,
        overlay_adjustments=_DEMO_OVERLAYS,
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
    )
    stock_scores, stage2_warnings = compute_stock_scores(
        stage1_result=stage1_result,
        stocks=_DEMO_STOCKS,
        disclosures=_DEMO_DISCLOSURES,
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


def build_scheduled_stub_context(trading_date: str, run_type: str) -> dict[str, str]:
    if run_type not in SCHEDULED_RUN_TIMES:
        raise ValueError(f"unsupported run type: {run_type}")

    trade_day = date.fromisoformat(trading_date)
    if not _is_trading_day(trade_day):
        raise ValueError(f"scheduled runs require a trading day: {trading_date}")
    as_of_timestamp = f"{trading_date}T{SCHEDULED_RUN_TIMES[run_type]}"
    if run_type == "pre_open":
        input_cutoff = f"{_previous_trading_day(trade_day).isoformat()}T18:00:00+09:00"
    else:
        input_cutoff = as_of_timestamp
    return {
        "run_id": f"{trading_date}-{run_type}",
        "run_type": run_type,
        "trading_date": trading_date,
        "as_of_timestamp": as_of_timestamp,
        "input_cutoff": input_cutoff,
        "published_at": as_of_timestamp,
    }


def run_scheduled_stub(
    output_dir: str | Path, *, trading_date: str, run_type: str
) -> dict[str, Any]:
    context = build_scheduled_stub_context(trading_date, run_type)
    result = run_demo(
        output_dir,
        run_id=context["run_id"],
        run_type=context["run_type"],
        as_of_timestamp=context["as_of_timestamp"],
        input_cutoff=context["input_cutoff"],
        published_at=context["published_at"],
    )
    return {"context": context, **result}


def iter_trading_dates(start_date: str, end_date: str) -> list[str]:
    current = date.fromisoformat(start_date)
    final = date.fromisoformat(end_date)
    if current > final:
        raise ValueError("start_date must be on or before end_date")

    trading_dates: list[str] = []
    while current <= final:
        iso_date = current.isoformat()
        if _is_trading_day(current):
            trading_dates.append(iso_date)
        current += timedelta(days=1)
    return trading_dates


def build_backtest_stub_plan(
    *, start_date: str, end_date: str, run_type: str = DEFAULT_BACKTEST_RUN_TYPE
) -> list[dict[str, str]]:
    return [
        build_scheduled_stub_context(trading_date=trading_date, run_type=run_type)
        for trading_date in iter_trading_dates(start_date, end_date)
    ]


def run_backtest_stub(
    output_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
) -> dict[str, Any]:
    plan = build_backtest_stub_plan(start_date=start_date, end_date=end_date, run_type=run_type)
    backtest_root = Path(output_dir) / "backtest" / f"{start_date}_{end_date}_{run_type}"
    runs = []
    for context in plan:
        result = run_demo(
            backtest_root,
            run_id=context["run_id"],
            run_type=context["run_type"],
            as_of_timestamp=context["as_of_timestamp"],
            input_cutoff=context["input_cutoff"],
            published_at=context["published_at"],
        )
        runs.append(
            {
                "run_id": context["run_id"],
                "trading_date": context["trading_date"],
                "status": result["snapshot"]["status"],
            }
        )
    return {
        "output_dir": str(backtest_root),
        "run_type": run_type,
        "trading_dates": [context["trading_date"] for context in plan],
        "runs": runs,
    }


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_sqlite(snapshot: Snapshot, database_path: Path) -> None:
    _ensure_parent(database_path)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                input_cutoff TEXT NOT NULL,
                published_at TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO snapshots (
                run_id,
                run_type,
                as_of_timestamp,
                input_cutoff,
                published_at,
                status,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.run_id,
                snapshot.run_type,
                snapshot.as_of_timestamp,
                snapshot.input_cutoff,
                snapshot.published_at,
                snapshot.status,
                json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def publish_snapshot(snapshot: Snapshot, output_dir: str | Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    snapshot_root = output_dir / "data" / "snapshots" / snapshot.run_id
    if snapshot_root.exists():
        raise FileExistsError(f"snapshot run already exists: {snapshot.run_id}")
    snapshot_root.mkdir(parents=True, exist_ok=False)

    industry_path = snapshot_root / "industry_scores.parquet"
    stock_path = snapshot_root / "stock_scores.parquet"
    snapshot_json_path = snapshot_root / "snapshot.json"
    latest_path = output_dir / "data" / "snapshots" / "latest.json"
    database_path = output_dir / "data" / "snapshots" / "mvp.sqlite"

    pd.DataFrame([score.to_dict() for score in snapshot.industry_scores]).to_parquet(
        industry_path, index=False
    )
    pd.DataFrame([score.to_dict() for score in snapshot.stock_scores]).to_parquet(
        stock_path, index=False
    )
    snapshot_json_path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_sqlite(snapshot, database_path)

    latest_payload = {
        "run_id": snapshot.run_id,
        "run_type": snapshot.run_type,
        "published_at": snapshot.published_at,
        "snapshot_json": str(snapshot_json_path),
        "industry_parquet": str(industry_path),
        "stock_parquet": str(stock_path),
    }
    _ensure_parent(latest_path)
    latest_path.write_text(
        json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {key: str(value) for key, value in latest_payload.items()}


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
