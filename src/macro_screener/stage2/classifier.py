from __future__ import annotations

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

IGNORED_TITLE_PATTERNS = (
    "사업보고서",
    "반기보고서",
    "분기보고서",
    "감사보고서",
    "첨부추가",
)


def classify_disclosure(event_code: str | None, title: str) -> str:
    """공시 제목과 이벤트를 분류한다."""
    if event_code and event_code in EVENT_CODE_MAP:
        return EVENT_CODE_MAP[event_code]
    normalized = title.strip().lower()
    if any(pattern.lower() in normalized for pattern in IGNORED_TITLE_PATTERNS):
        return "ignored"
    for block_name, patterns in TITLE_PATTERNS:
        if any(pattern.lower() in normalized for pattern in patterns):
            return block_name
    return "neutral"
