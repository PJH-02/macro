from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
INDUSTRY_MASTER_FIELDS: tuple[str, ...] = (
    "industry_code",
    "industry_name",
    "sector_l1",
    "sector_l2",
    "sector_l3",
    "stock_count",
    "representative_stock_code",
    "source_classification_version",
    "generated_at",
)
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {channel: 1.0 for channel in CHANNELS}
DEFAULT_NEUTRAL_BANDS: dict[str, float] = {
    "G": 0.25,
    "IC": 0.25,
    "FC": 0.25,
    "ED": 0.25,
    "FX": 0.50,
}

PROFILE_RULES: dict[str, dict[str, dict[str, float]]] = {
    "G": {
        "pos": {
            "반도체": 6.0,
            "전자": 5.0,
            "디스플레이": 4.0,
            "자동차": 5.0,
            "운송장비": 4.0,
            "조선": 5.0,
            "기계": 4.0,
            "화학": 2.0,
            "제조": 1.5,
            "소프트웨어": 2.5,
        },
        "neg": {
            "유틸리티": 5.0,
            "통신": 4.0,
            "음식료": 3.0,
            "담배": 3.0,
            "보험": 2.0,
            "부동산": 3.0,
            "리츠": 4.0,
            "공공": 3.0,
        },
    },
    "IC": {
        "pos": {
            "에너지": 6.0,
            "석유": 5.0,
            "가스": 4.0,
            "화학": 4.0,
            "철강": 5.0,
            "금속": 4.0,
            "광업": 4.0,
            "비철": 4.0,
        },
        "neg": {
            "항공": 6.0,
            "운송": 3.0,
            "유통": 4.0,
            "소매": 4.0,
            "음식료": 4.0,
            "제약": 2.0,
            "전기": 2.0,
            "가구": 2.0,
        },
    },
    "FC": {
        "pos": {
            "증권": 5.0,
            "금융": 4.0,
            "건설": 4.0,
            "부동산": 4.0,
            "기계": 2.0,
            "소프트웨어": 2.0,
            "IT": 2.0,
        },
        "neg": {
            "보험": 4.0,
            "통신": 3.0,
            "유틸리티": 4.0,
            "음식료": 2.0,
            "공공": 3.0,
            "제약": 2.0,
        },
    },
    "ED": {
        "pos": {
            "반도체": 6.0,
            "전자": 5.0,
            "자동차": 6.0,
            "조선": 6.0,
            "기계": 4.0,
            "화학": 3.0,
            "철강": 3.0,
            "운송장비": 4.0,
        },
        "neg": {
            "유통": 4.0,
            "음식료": 4.0,
            "통신": 3.0,
            "보험": 2.0,
            "교육": 3.0,
            "미디어": 2.0,
            "건강": 2.0,
            "헬스": 2.0,
        },
    },
    "FX": {
        "pos": {
            "반도체": 6.0,
            "전자": 5.0,
            "자동차": 5.0,
            "조선": 5.0,
            "기계": 4.0,
            "화학": 2.0,
            "디스플레이": 3.0,
        },
        "neg": {
            "항공": 6.0,
            "유통": 4.0,
            "소매": 4.0,
            "유틸리티": 3.0,
            "가스": 3.0,
            "음식료": 3.0,
            "제약": 2.0,
        },
    },
}


def _iso_utc_now() -> str:
    """현재 UTC 시각 문자열을 반환한다."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_path_text(path: Path) -> str:
    """표준 경로 텍스트을 처리한다."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_slug_part(value: str) -> str:
    """slug part을 정규화한다"""
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = normalized.replace("·", " ")
    normalized = re.sub(r"[>/]+", " ", normalized)
    normalized = re.sub(r"[\s_]+", "-", normalized)
    normalized = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "na"


def industry_code_slug(parts: Sequence[str]) -> str:
    """업종 코드 slug을 처리한다."""
    return "__".join(_normalize_slug_part(part) for part in parts)


def classification_version(classification_path: Path) -> str:
    """분류 버전 식별자를 계산한다."""
    digest = hashlib.sha256(classification_path.read_bytes()).hexdigest()
    return f"stock-classification-sha256:{digest[:12]}"


def _read_classification_rows(classification_path: Path) -> list[dict[str, str]]:
    """read 분류 행을 처리한다."""
    with classification_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: str(value or "").strip() for key, value in row.items()} for row in reader]


def build_industry_master_records(
    classification_path: Path,
    *,
    generated_at: str | None = None,
) -> list[dict[str, str]]:
    """업종 마스터 레코드를 구성한다."""
    rows = _read_classification_rows(classification_path)
    source_version = classification_version(classification_path)
    generated_at_value = generated_at or _iso_utc_now()
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}

    for row in rows:
        sector_l1 = row.get("대분류", "")
        sector_l2 = row.get("중분류", "")
        sector_l3 = row.get("소분류", "")
        stock_code = row.get("종목코드", "").zfill(6)
        stock_name = row.get("종목명", "")
        if not sector_l1 or not sector_l2 or not sector_l3 or not stock_code or not stock_name:
            continue
        grouped.setdefault((sector_l1, sector_l2, sector_l3), []).append(row)

    records: list[dict[str, str]] = []
    for sector_key, sector_rows in sorted(grouped.items()):
        sector_l1, sector_l2, sector_l3 = sector_key
        representative = min(
            (row.get("종목코드", "").zfill(6) for row in sector_rows if row.get("종목코드")),
            default="",
        )
        records.append(
            {
                "industry_code": industry_code_slug(sector_key),
                "industry_name": sector_l3,
                "sector_l1": sector_l1,
                "sector_l2": sector_l2,
                "sector_l3": sector_l3,
                "stock_count": str(len(sector_rows)),
                "representative_stock_code": representative,
                "source_classification_version": source_version,
                "generated_at": generated_at_value,
            }
        )
    return records


def write_industry_master_csv(classification_path: Path, output_path: Path) -> list[dict[str, str]]:
    """업종 마스터 CSV를 기록한다."""
    records = build_industry_master_records(classification_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INDUSTRY_MASTER_FIELDS))
        writer.writeheader()
        writer.writerows(records)
    return records


def load_industry_master_records(industry_master_path: Path) -> list[dict[str, str]]:
    """업종 마스터 레코드를 불러온다."""
    with industry_master_path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _profile_text(industry: dict[str, str]) -> str:
    """프로필 텍스트을 처리한다."""
    return " ".join(
        [
            industry.get("industry_name", ""),
            industry.get("sector_l1", ""),
            industry.get("sector_l2", ""),
            industry.get("sector_l3", ""),
        ]
    )


def _profile_score(industry: dict[str, str], rules: dict[str, float]) -> float:
    """프로필 점수을 처리한다."""
    text = _profile_text(industry)
    return sum(weight for keyword, weight in rules.items() if keyword and keyword in text)


def _rank_industries(
    industries: Iterable[dict[str, str]],
    *,
    channel: str,
    regime: str,
) -> list[str]:
    """업종 후보를 점수 기준으로 정렬한다."""
    rules = PROFILE_RULES[channel][regime]
    ranked = sorted(
        industries,
        key=lambda industry: (
            -_profile_score(industry, rules),
            -int(industry["stock_count"]),
            industry["industry_code"],
        ),
    )
    return [industry["industry_code"] for industry in ranked]




def load_stage1_artifact(path: Path) -> dict[str, Any]:
    """stage1 산출물을 불러온다"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stage1 artifact must be a mapping")
    return payload

def build_provisional_stage1_artifact(
    industry_master_path: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """임시 1단계 산출물을 구성한다."""
    industries = load_industry_master_records(industry_master_path)
    if not industries:
        raise ValueError("industry master must contain at least one industry")
    source_version = industries[0]["source_classification_version"]
    generated_at_value = generated_at or _iso_utc_now()
    return {
        "artifact_version": "stage1-provisional-v1",
        "artifact_status": "provisional",
        "artifact_note": (
            "Bootstrap artifact generated from industry taxonomy with deterministic keyword "
            "heuristics; replace after research review."
        ),
        "generated_at": generated_at_value,
        "industry_master_path": _canonical_path_text(industry_master_path),
        "source_classification_version": source_version,
        "channel_weights": dict(DEFAULT_CHANNEL_WEIGHTS),
        "neutral_bands": dict(DEFAULT_NEUTRAL_BANDS),
        "sector_rank_tables": {
            channel: {
                "pos": _rank_industries(industries, channel=channel, regime="pos"),
                "neg": _rank_industries(industries, channel=channel, regime="neg"),
            }
            for channel in CHANNELS
        },
    }


def write_stage1_artifact_json(industry_master_path: Path, output_path: Path) -> dict[str, Any]:
    """1단계 산출물 JSON을 기록한다."""
    artifact = build_provisional_stage1_artifact(industry_master_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact
