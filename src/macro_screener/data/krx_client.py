from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.data.reference import industry_code_slug

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

NON_COMMON_STOCK_KEYWORDS = ("ETF", "ETN", "REIT", "리츠", "SPAC", "스팩")


@dataclass(frozen=True, slots=True)
class KRXLoadResult:
    rows: list[dict[str, Any]]
    source: str
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class KRXClient:
    stock_classification_path: Path | None = None
    exposure_matrix_path: Path = Path("data/industry_exposures.json")
    ohlcv_path: Path = Path("data/ohlcv.csv")
    use_demo_fallback: bool = True

    def load_demo_exposures(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_EXPOSURES]

    def load_demo_stocks(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_STOCKS]

    def load_exposures(self) -> list[dict[str, Any]]:
        return self.load_exposures_result().rows

    def load_exposures_result(self) -> KRXLoadResult:
        if self.exposure_matrix_path.exists():
            payload = json.loads(self.exposure_matrix_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return KRXLoadResult(
                    rows=[dict(item) for item in payload],
                    source="file",
                    warnings=[],
                )
        if self.use_demo_fallback:
            return KRXLoadResult(
                rows=self.load_demo_exposures(),
                source="demo",
                warnings=["krx_exposure_matrix_missing_using_demo_fallback"],
            )
        return KRXLoadResult(
            rows=[],
            source="unavailable",
            warnings=["krx_exposure_matrix_missing"],
        )

    def load_stock_classification(self) -> pd.DataFrame:
        if self.stock_classification_path is None or not self.stock_classification_path.exists():
            return pd.DataFrame(columns=["종목코드", "종목명", "대분류", "중분류", "소분류"])
        return pd.read_csv(self.stock_classification_path, dtype=str).fillna("")

    def load_stocks(self) -> list[dict[str, Any]]:
        return self.load_stocks_result().rows

    def load_stocks_result(self) -> KRXLoadResult:
        frame = self.load_stock_classification()
        if frame.empty:
            if self.use_demo_fallback:
                return KRXLoadResult(
                    rows=self.load_demo_stocks(),
                    source="demo",
                    warnings=["stock_classification_missing_using_demo_fallback"],
                )
            return KRXLoadResult(
                rows=[],
                source="unavailable",
                warnings=["stock_classification_missing"],
            )
        rows: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            stock_code = self._first_value(row, "stock_code", "종목코드", "code")
            stock_name = self._first_value(row, "stock_name", "종목명", "name")
            sector_l1 = self._first_value(row, "sector_l1", "대분류")
            sector_l2 = self._first_value(row, "sector_l2", "중분류")
            sector_l3 = self._first_value(row, "sector_l3", "소분류")
            if sector_l1 and sector_l2 and sector_l3:
                industry_code = industry_code_slug((sector_l1, sector_l2, sector_l3))
            else:
                industry_code = self._first_value(
                    row, "industry_code", "industry", "소분류", "중분류", "대분류"
                )
            security_type = self._first_value(row, "security_type", "증권구분", "종목구분")
            if not stock_code or not stock_name or not industry_code:
                continue
            if self._is_non_common_equity(stock_name=stock_name, security_type=security_type):
                continue
            rows.append(
                {
                    "stock_code": stock_code.zfill(6),
                    "stock_name": stock_name,
                    "industry_code": industry_code,
                }
            )
        if rows:
            return KRXLoadResult(rows=rows, source="file", warnings=[])
        if self.use_demo_fallback:
            return KRXLoadResult(
                rows=self.load_demo_stocks(),
                source="demo",
                warnings=["stock_classification_empty_using_demo_fallback"],
            )
        return KRXLoadResult(
            rows=[],
            source="unavailable",
            warnings=["stock_classification_empty"],
        )

    def load_ohlcv(self) -> pd.DataFrame:
        if not self.ohlcv_path.exists():
            return pd.DataFrame(
                columns=["stock_code", "trading_date", "open", "high", "low", "close", "volume"]
            )
        return pd.read_csv(self.ohlcv_path)

    @staticmethod
    def _first_value(row: pd.Series, *columns: str) -> str:
        for column in columns:
            value = row.get(column)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _is_non_common_equity(*, stock_name: str, security_type: str) -> bool:
        upper_name = stock_name.upper()
        upper_type = security_type.upper()
        return any(
            keyword in upper_name or keyword in upper_type
            for keyword in NON_COMMON_STOCK_KEYWORDS
        )
