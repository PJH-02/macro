from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from macro_screener.config.loader import repo_root

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

GROUPED_SECTORS: tuple[str, ...] = (
    "반도체",
    "반도체장비",
    "기계",
    "자동차/부품",
    "조선",
    "철강",
    "화학",
    "IT하드웨어/디스플레이/전자부품",
    "건설/건자재",
    "해운/물류",
    "증권",
    "은행",
    "비철/산업금속",
    "항공",
    "내구소비재/의류/화장품",
    "여행/레저",
    "에너지(정유/가스)",
    "방산",
    "소프트웨어/인터넷/게임",
    "보험",
    "유통/소매",
    "헬스케어/바이오",
    "리츠/부동산",
    "필수소비재(음식료)",
    "통신",
    "유틸리티",
)

GROUPED_SECTOR_EXPOSURE_MATRIX: dict[str, dict[str, int]] = {
    "G": {"반도체": 12, "반도체장비": 11, "기계": 10, "자동차/부품": 9, "조선": 8, "철강": 7, "화학": 6, "IT하드웨어/디스플레이/전자부품": 5, "건설/건자재": 4, "해운/물류": 3, "증권": 2, "은행": 1, "비철/산업금속": 0, "항공": 0, "내구소비재/의류/화장품": -1, "여행/레저": -2, "에너지(정유/가스)": -3, "방산": -4, "소프트웨어/인터넷/게임": -5, "보험": -6, "유통/소매": -7, "헬스케어/바이오": -8, "리츠/부동산": -9, "필수소비재(음식료)": -10, "통신": -11, "유틸리티": -12},
    "IC": {"에너지(정유/가스)": 12, "비철/산업금속": 11, "철강": 10, "조선": 9, "방산": 8, "해운/물류": 7, "은행": 6, "건설/건자재": 5, "자동차/부품": 4, "기계": 3, "반도체": 2, "IT하드웨어/디스플레이/전자부품": 1, "증권": 0, "리츠/부동산": 0, "헬스케어/바이오": -1, "소프트웨어/인터넷/게임": -2, "통신": -3, "보험": -4, "반도체장비": -5, "화학": -6, "내구소비재/의류/화장품": -7, "유통/소매": -8, "필수소비재(음식료)": -9, "유틸리티": -10, "여행/레저": -11, "항공": -12},
    "FC": {"소프트웨어/인터넷/게임": 12, "헬스케어/바이오": 11, "반도체장비": 10, "리츠/부동산": 9, "건설/건자재": 8, "증권": 7, "반도체": 6, "IT하드웨어/디스플레이/전자부품": 5, "내구소비재/의류/화장품": 4, "유통/소매": 3, "여행/레저": 2, "항공": 1, "통신": 0, "유틸리티": 0, "조선": -1, "기계": -2, "자동차/부품": -3, "방산": -4, "해운/물류": -5, "화학": -6, "필수소비재(음식료)": -7, "비철/산업금속": -8, "철강": -9, "에너지(정유/가스)": -10, "보험": -11, "은행": -12},
    "ED": {"반도체": 12, "반도체장비": 11, "IT하드웨어/디스플레이/전자부품": 10, "기계": 9, "자동차/부품": 8, "조선": 7, "방산": 6, "화학": 5, "철강": 4, "해운/물류": 3, "비철/산업금속": 2, "에너지(정유/가스)": 1, "건설/건자재": 0, "은행": 0, "증권": -1, "소프트웨어/인터넷/게임": -2, "헬스케어/바이오": -3, "항공": -4, "보험": -5, "내구소비재/의류/화장품": -6, "여행/레저": -7, "유통/소매": -8, "필수소비재(음식료)": -9, "통신": -10, "유틸리티": -11, "리츠/부동산": -12},
    "FX": {"반도체": 12, "조선": 11, "자동차/부품": 10, "기계": 9, "방산": 8, "반도체장비": 7, "철강": 6, "비철/산업금속": 5, "해운/물류": 4, "IT하드웨어/디스플레이/전자부품": 3, "에너지(정유/가스)": 2, "은행": 1, "헬스케어/바이오": 0, "건설/건자재": 0, "소프트웨어/인터넷/게임": -1, "보험": -2, "통신": -3, "증권": -4, "필수소비재(음식료)": -5, "화학": -6, "리츠/부동산": -7, "내구소비재/의류/화장품": -8, "유틸리티": -9, "유통/소매": -10, "여행/레저": -11, "항공": -12},
}

SMALL_LABEL_TO_GROUPED_SECTOR: dict[str, str | None] = {
    "가구": "내구소비재/의류/화장품", "가스": "유틸리티", "가전/전자제품": "IT하드웨어/디스플레이/전자부품", "가정용 기기": "내구소비재/의류/화장품", "가죽, 가방 및 유사제품": "내구소비재/의류/화장품", "개인 및 가정용품 수리": "유통/소매", "개인 및 가정용품 임대": "유통/소매", "건물설비 설치 공사": "건설/건자재", "건설": "건설/건자재", "건축기술, 엔지니어링 및 관련 기술 서비스": "건설/건자재", "건축자재, 철물 및 난방장치 도매": "건설/건자재", "고무제품": "화학", "곡물가공품, 전분 및 전분제품": "필수소비재(음식료)", "골판지, 종이 상자 및 종이용기": "건설/건자재", "과실, 채소 가공 및 저장 처리": "필수소비재(음식료)", "광고/마케팅": "소프트웨어/인터넷/게임", "교육지원 서비스": "소프트웨어/인터넷/게임", "구조용 금속제품, 탱크 및 증기발생기": "비철/산업금속", "귀금속 및 장신용품": "내구소비재/의류/화장품", "그외 기타 개인 서비스": "유통/소매", "그외 기타 운송장비": "항공", "그외 기타 전문, 과학 및 기술 서비스": "소프트웨어/인터넷/게임", "그외 기타 제품": "내구소비재/의류/화장품", "금속": "비철/산업금속", "금속 주조": "비철/산업금속", "금속가공": "비철/산업금속", "금융": "증권", "금융 지원 서비스": "유통/소매", "기계장비 및 관련 물품 도매": "기계", "기록매체 복제": "소프트웨어/인터넷/게임", "기반조성 및 시설물 축조관련 전문공사": "건설/건자재", "기초 의약물질": "헬스케어/바이오", "기타 과학기술 서비스": "소프트웨어/인터넷/게임", "기타 교육기관": "소프트웨어/인터넷/게임", "기타 금융": "증권", "기타 비금속 광물제품": "건설/건자재", "기타 사지원 서비스": "유통/소매", "기타 상품 전문 소매": "유통/소매", "기타 생활용품 소매": "유통/소매", "기타 식품": "필수소비재(음식료)", "기타 운송관련 서비스": "해운/물류", "기타 전기장비": "IT하드웨어/디스플레이/전자부품", "기타 전문 도매": "유통/소매", "기타 전문 서비스": "소프트웨어/인터넷/게임", "기타 정보 서비스": "소프트웨어/인터넷/게임", "기타 화학제품": "화학", "나무제품": "건설/건자재", "내화, 비내화 요제품": "건설/건자재", "도로 화물 운송": "해운/물류", "도시락 및 식사용 조리식품": "필수소비재(음식료)", "도축, 육류 가공 및 저장 처리": "필수소비재(음식료)", "동·식물성 유지 및 낙농제품": "필수소비재(음식료)", "동물용 사료 및 조제식품": "필수소비재(음식료)", "디스플레이": "IT하드웨어/디스플레이/전자부품", "떡, 빵 및 과자류": "필수소비재(음식료)", "레저": "여행/레저", "마그네틱 및 광학 매체": "IT하드웨어/디스플레이/전자부품", "무기 및 총포탄": "방산", "무점포 소매": "유통/소매", "미디어/콘텐츠": "소프트웨어/인터넷/게임", "미디어/통신": "통신", "바이오": "헬스케어/바이오", "반도체": "반도체", "방적 및 가공사": "내구소비재/의류/화장품", "보험": "보험", "부동산 임대 및 공급": "리츠/부동산", "비료, 농약 및 살균, 살충제": "화학", "비철금속": "비철/산업금속", "사시설 유지·관리 서비스": "유틸리티", "사진장비 및 광학기기": "IT하드웨어/디스플레이/전자부품", "산용 기계 및 장비 임대": "기계", "산용 농·축산물 및 동·식물 도매": "유통/소매", "상품 종합 도매": "유통/소매", "상품 중개": "유통/소매", "생활용품 도매": "유통/소매", "서적, 잡지 및 기타 인쇄물 출판": "소프트웨어/인터넷/게임", "섬유/의류": "내구소비재/의류/화장품", "소프트웨어": "소프트웨어/인터넷/게임", "수산물 가공 및 저장 처리": "필수소비재(음식료)", "스포츠 서비스": "여행/레저", "시멘트, 석회, 플라스터 및 그 제품": "건설/건자재", "시장조사 및 여론조사": "소프트웨어/인터넷/게임", "신발 및 신발 부분품": "내구소비재/의류/화장품", "신탁 및 집합투자": "증권", "실내건축 및 건축마무리 공사": "건설/건자재", "악기": "내구소비재/의류/화장품", "어로 어": "필수소비재(음식료)", "에너지/화학": "에너지(정유/가스)", "여행": "여행/레저", "연료 소매": "에너지(정유/가스)", "오디오물 출판 및 원판 녹음": "여행/레저", "오락·문화": "여행/레저", "운동 및 경기용구": "내구소비재/의류/화장품", "운송": "해운/물류", "운송장비 임대": "해운/물류", "유리 및 유리제품": "건설/건자재", "유통": "유통/소매", "육상 여객 운송": "해운/물류", "은행": "은행", "음식료": "필수소비재(음식료)", "음식점": "필수소비재(음식료)", "의료기기": "헬스케어/바이오", "의료용품 및 기타 의약 관련제품": "헬스케어/바이오", "이차전지": "IT하드웨어/디스플레이/전자부품", "인쇄 및 인쇄관련 산": "소프트웨어/인터넷/게임", "인터넷서비스": "소프트웨어/인터넷/게임", "일반 교습 학원": "소프트웨어/인터넷/게임", "일반 목적용 기계": "기계", "자동차": "자동차/부품", "자동차 부품 및 내장품 판매": "자동차/부품", "자동차 재제조 부품": "자동차/부품", "자동차 차체나 트레일러": "자동차/부품", "자동차 판매": "자동차/부품", "자동차부품": "자동차/부품", "작물 재배": "필수소비재(음식료)", "전구 및 조명장치": "IT하드웨어/디스플레이/전자부품", "전기 및 통신 공사": "건설/건자재", "전기 통신": "통신", "전기·전자": "IT하드웨어/디스플레이/전자부품", "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치": "IT하드웨어/디스플레이/전자부품", "전력": "유틸리티", "전문디자인": "소프트웨어/인터넷/게임", "전자부품": "IT하드웨어/디스플레이/전자부품", "절연선 및 케이블": "IT하드웨어/디스플레이/전자부품", "정유": "에너지(정유/가스)", "제약": "헬스케어/바이오", "제재 및 목재 가공": "건설/건자재", "조선": "조선", "종이/포장": "건설/건자재", "증권": "증권", "증기, 냉·온수 및 공기조절 공급": "유틸리티", "직물직조 및 직물제품": "내구소비재/의류/화장품", "창작 및 예술관련 서비스": "여행/레저", "철강": "철강", "초등 교육기관": "소프트웨어/인터넷/게임", "측정, 시험, 항해, 제어 및 기타 정밀기기; 광학기기 제외": "헬스케어/바이오", "컴퓨터 및 주변장치": "IT하드웨어/디스플레이/전자부품", "통신장비": "IT하드웨어/디스플레이/전자부품", "특수 목적용 기계": "기계", "편조원단": "내구소비재/의류/화장품", "폐기물 처리": "유틸리티", "플라스틱제품": "화학", "항공 여객 운송": "항공", "항공기,우주선 및 부품": "항공", "해운": "해운/물류", "호텔/레저": "여행/레저", "화장품": "내구소비재/의류/화장품", "화학": "화학", "화학섬유": "화학", "회사 본부 및 경영 컨설팅 서비스": "소프트웨어/인터넷/게임",
}


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_path_text(path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_slug_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower().replace("·", " ")
    normalized = re.sub(r"[>/]+", " ", normalized)
    normalized = re.sub(r"[\s_]+", "-", normalized)
    normalized = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "na"


def industry_code_slug(parts: Sequence[str]) -> str:
    return "__".join(_normalize_slug_part(part) for part in parts)


def grouped_sector_code(sector_name: str) -> str:
    return industry_code_slug((sector_name,))


def classification_version(classification_path: Path) -> str:
    digest = hashlib.sha256(classification_path.read_bytes()).hexdigest()
    return f"stock-classification-sha256:{digest[:12]}"


def _read_classification_rows(classification_path: Path) -> list[dict[str, str]]:
    with classification_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: str(value or "").strip() for key, value in row.items()} for row in reader]


def map_small_label_to_grouped_sector(label: str) -> str | None:
    return SMALL_LABEL_TO_GROUPED_SECTOR.get(label.strip())


def map_classification_row_to_grouped_sector(row: dict[str, str]) -> str | None:
    for key in ("소분류", "sector_l3", "industry_name"):
        value = str(row.get(key, "")).strip()
        if value:
            mapped = map_small_label_to_grouped_sector(value)
            if mapped is not None:
                return mapped
    return None


def build_stock_sector_rows(classification_path: Path) -> list[dict[str, str]]:
    rows = _read_classification_rows(classification_path)
    stock_rows: list[dict[str, str]] = []
    for row in rows:
        stock_code = str(row.get("종목코드", "")).zfill(6)
        stock_name = str(row.get("종목명", "")).strip()
        grouped_sector = map_classification_row_to_grouped_sector(row)
        stock_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "sector_l1": str(row.get("대분류", "")).strip(),
                "sector_l2": str(row.get("중분류", "")).strip(),
                "sector_l3": str(row.get("소분류", "")).strip(),
                "grouped_sector": grouped_sector or "",
                "grouped_sector_code": grouped_sector_code(grouped_sector) if grouped_sector else "",
                "mapping_review_required": "true" if grouped_sector is None else "false",
            }
        )
    return stock_rows


def build_industry_master_records(classification_path: Path, *, generated_at: str | None = None) -> list[dict[str, str]]:
    source_version = classification_version(classification_path)
    generated_at_value = generated_at or _iso_utc_now()
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in build_stock_sector_rows(classification_path):
        sector_name = row["grouped_sector"]
        if not sector_name:
            continue
        grouped.setdefault(sector_name, []).append(row)
    records: list[dict[str, str]] = []
    for sector_name in GROUPED_SECTORS:
        sector_rows = grouped.get(sector_name, [])
        if not sector_rows:
            continue
        representative = min((row["stock_code"] for row in sector_rows if row["stock_code"]), default="")
        records.append(
            {
                "industry_code": grouped_sector_code(sector_name),
                "industry_name": sector_name,
                "sector_l1": sector_name,
                "sector_l2": "grouped_sector",
                "sector_l3": sector_name,
                "stock_count": str(len(sector_rows)),
                "representative_stock_code": representative,
                "source_classification_version": source_version,
                "generated_at": generated_at_value,
            }
        )
    return records


def write_industry_master_csv(classification_path: Path, output_path: Path) -> list[dict[str, str]]:
    records = build_industry_master_records(classification_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INDUSTRY_MASTER_FIELDS))
        writer.writeheader()
        writer.writerows(records)
    return records


def load_industry_master_records(industry_master_path: Path) -> list[dict[str, str]]:
    with industry_master_path.open("r", encoding="utf-8", newline="") as handle:
        return [{key: str(value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def load_stage1_artifact(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stage1 artifact must be a mapping")
    return payload


def build_grouped_sector_rank_table_compat_artifact() -> dict[str, Any]:
    sector_rank_tables = {
        channel: {
            "pos": list(sector_scores),
            "neg": list(reversed(list(sector_scores))),
        }
        for channel, sector_scores in GROUPED_SECTOR_EXPOSURE_MATRIX.items()
    }
    return {
        "artifact_version": "stage1-grouped-sector-compat-v1",
        "artifact_status": "compatibility",
        "artifact_note": (
            "Compatibility rank-table view derived from config/macro_sector_exposure.v2.json. "
            "Stage 1 final sector scores are calculated from the exposure values in that file, "
            "not from this artifact."
        ),
        "source_artifact_path": "config/macro_sector_exposure.v2.json",
        "channel_weights": dict(DEFAULT_CHANNEL_WEIGHTS),
        "neutral_bands": dict(DEFAULT_NEUTRAL_BANDS),
        "sector_rank_tables": sector_rank_tables,
    }


def build_provisional_stage1_artifact(industry_master_path: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    industries = load_industry_master_records(industry_master_path)
    if not industries:
        raise ValueError("industry master must contain at least one grouped sector")
    source_version = industries[0]["source_classification_version"]
    generated_at_value = generated_at or _iso_utc_now()
    return {
        "artifact_version": "macro-sector-exposure-v2",
        "artifact_status": "authoritative",
        "generated_at": generated_at_value,
        "industry_master_path": _canonical_path_text(industry_master_path),
        "source_classification_version": source_version,
        "channel_weights": dict(DEFAULT_CHANNEL_WEIGHTS),
        "neutral_bands": dict(DEFAULT_NEUTRAL_BANDS),
        "sector_exposure": GROUPED_SECTOR_EXPOSURE_MATRIX,
    }


def write_stage1_artifact_json(industry_master_path: Path, output_path: Path) -> dict[str, Any]:
    artifact = build_provisional_stage1_artifact(industry_master_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact
