from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_DISCLOSURES: list[dict[str, Any]] = [
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
    {
        "stock_code": "009540",
        "event_code": None,
        "title": "정정 공시",
        "trading_days_elapsed": 1,
    },
    {
        "stock_code": "000100",
        "event_code": None,
        "title": "설명회 개최",
        "trading_days_elapsed": 0,
    },
]


@dataclass(frozen=True, slots=True)
class DARTClient:
    def load_demo_disclosures(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_DISCLOSURES]
