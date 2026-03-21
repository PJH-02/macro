from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_EXPOSURES: list[dict[str, Any]] = [
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

DEFAULT_STOCKS: list[dict[str, Any]] = [
    {"stock_code": "000270", "stock_name": "Kia", "industry_code": "AUTO"},
    {"stock_code": "005380", "stock_name": "Hyundai Motor", "industry_code": "AUTO"},
    {"stock_code": "009540", "stock_name": "HD Korea Shipbuilding", "industry_code": "SHIP"},
    {"stock_code": "000100", "stock_name": "Yuhan", "industry_code": "PHARMA"},
]


@dataclass(frozen=True, slots=True)
class KRXClient:
    stock_classification_path: Path | None = None

    def load_demo_exposures(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_EXPOSURES]

    def load_demo_stocks(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_STOCKS]

    def load_stock_classification(self) -> pd.DataFrame:
        if self.stock_classification_path is None or not self.stock_classification_path.exists():
            return pd.DataFrame(columns=["종목코드", "종목명", "대분류", "중분류", "소분류"])
        return pd.read_csv(self.stock_classification_path, dtype=str)
