from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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
LIVE_STOCK_MASTER_SERVICE_FAMILY = "유가증권 종목기본정보"


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
    api_key_env: str = "KRX_API_KEY"
    use_demo_fallback: bool = True
    allowed_markets: tuple[str, ...] = DEFAULT_ALLOWED_MARKETS

    @staticmethod
    def build_live_stock_master_request(*, auth_key: str, bas_dd: str) -> dict[str, Any]:
        return {
            "provider": "krx",
            "service_family": DEFAULT_LIVE_SERVICE_FAMILY,
            "transport": {
                "headers": {"AUTH_KEY": auth_key},
                "response_format": "json",
            },
            "params": {"basDd": bas_dd},
        }

    def normalize_live_stock_master_response(self, payload: Mapping[str, Any]) -> KRXLoadResult:
        provider = str(payload.get("provider") or "krx").strip().lower()
        if provider != "krx":
            raise ValueError(f"unexpected KRX provider payload: {provider}")
        service_family = str(
            payload.get("service_family") or DEFAULT_LIVE_SERVICE_FAMILY
        ).strip()
        if service_family != DEFAULT_LIVE_SERVICE_FAMILY:
            raise ValueError(f"unexpected KRX service family: {service_family}")
        raw_records = payload.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("KRX live stock master payload must contain a records list")
        records = [dict(item) for item in raw_records if isinstance(item, Mapping)]
        return self.normalize_live_stock_records(records)

    def normalize_live_stock_records(self, records: list[dict[str, Any]]) -> KRXLoadResult:
        classification = self.load_stock_classification()
        if classification.empty:
            return KRXLoadResult(
                rows=[],
                source="live",
                warnings=["stock_classification_missing_for_live_join"],
            )

        taxonomy_by_code = self._classification_lookup(classification)
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []
        for record in records:
            stock_code = str(record.get("stock_code") or "").strip().zfill(6)
            stock_name = str(record.get("stock_name") or "").strip()
            market = str(record.get("market") or "").strip().upper()
            security_type = str(record.get("security_type") or "").strip()
            listing_status = str(record.get("listing_status") or "").strip()
            if not stock_code:
                continue
            if market and market not in self.allowed_markets:
                continue
            if not self._is_live_record_listed_common(
                stock_name=stock_name,
                security_type=security_type,
                listing_status=listing_status,
            ):
                continue
            classification_row = taxonomy_by_code.get(stock_code)
            if classification_row is None:
                warnings.append(f"krx_live_row_missing_taxonomy:{stock_code}")
                continue
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name or classification_row["stock_name"],
                    "industry_code": classification_row["industry_code"],
                }
            )
        return KRXLoadResult(
            rows=rows,
            source="live",
            warnings=list(dict.fromkeys(warnings)),
        )

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

    def build_live_stock_master_request(
        self,
        *,
        trading_date: str,
        auth_key: str | None = None,
    ) -> dict[str, Any]:
        resolved_auth_key = (auth_key or os.getenv(self.api_key_env, "")).strip()
        if not resolved_auth_key:
            raise ValueError(f"Missing KRX auth key env: {self.api_key_env}")
        return {
            "provider": "krx",
            "service_family": LIVE_STOCK_MASTER_SERVICE_FAMILY,
            "transport": {
                "headers": {"AUTH_KEY": resolved_auth_key},
                "response_format": "json",
            },
            "params": {"basDd": trading_date},
        }

    def load_live_stocks_result(
        self,
        *,
        trading_date: str,
        fetcher: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> KRXLoadResult:
        auth_key = os.getenv(self.api_key_env, "").strip()
        if not auth_key:
            return KRXLoadResult(
                rows=[],
                source="unavailable",
                warnings=["krx_live_source_unconfigured"],
            )
        if fetcher is None:
            return KRXLoadResult(
                rows=[],
                source="unavailable",
                warnings=["krx_live_fetcher_unconfigured"],
            )
        try:
            request_payload = self.build_live_stock_master_request(
                trading_date=trading_date,
                auth_key=auth_key,
            )
            live_rows = self._normalize_live_stock_master_response(fetcher(request_payload))
        except Exception as exc:
            return KRXLoadResult(
                rows=[],
                source="unavailable",
                warnings=[f"krx_live_fetch_failed: {exc}"],
            )
        if not live_rows:
            return KRXLoadResult(
                rows=[],
                source="unavailable",
                warnings=["krx_live_records_empty"],
            )

        frame = self.load_stock_classification()
        taxonomy_rows = self._classification_rows(frame)
        if not taxonomy_rows:
            warning = self._classification_unavailable_warning(frame)
            return KRXLoadResult(rows=[], source="unavailable", warnings=[warning])

        taxonomy_by_code = {row["stock_code"]: row for row in taxonomy_rows}
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        missing_taxonomy = 0

        for live_row in live_rows:
            stock_code = str(live_row["stock_code"]).zfill(6)
            taxonomy_row = taxonomy_by_code.get(stock_code)
            if taxonomy_row is None:
                missing_taxonomy += 1
                continue
            stock_name = str(live_row.get("stock_name") or taxonomy_row["stock_name"]).strip()
            security_type = str(
                live_row.get("security_type") or taxonomy_row.get("security_type", "")
            ).strip()
            listing_status = str(live_row.get("listing_status") or "LISTED").strip().upper()
            if listing_status and listing_status not in {"LISTED", "상장"}:
                continue
            if not stock_name or self._is_non_common_equity(
                stock_name=stock_name,
                security_type=security_type,
            ):
                continue
            if stock_code in seen_codes:
                continue
            seen_codes.add(stock_code)
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "industry_code": str(taxonomy_row["industry_code"]),
                }
            )

        if missing_taxonomy:
            warnings.append(f"krx_live_rows_missing_taxonomy_mapping={missing_taxonomy}")
        if rows:
            return KRXLoadResult(rows=rows, source="live", warnings=warnings)
        return KRXLoadResult(
            rows=[],
            source="unavailable",
            warnings=[*warnings, "krx_live_rows_unusable_after_taxonomy_join"],
        )

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
        classification_rows = self._classification_rows(frame)
        rows = [
            {
                "stock_code": str(row["stock_code"]),
                "stock_name": str(row["stock_name"]),
                "industry_code": str(row["industry_code"]),
            }
            for row in classification_rows
        ]
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

    def _classification_rows(self, frame: pd.DataFrame) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
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
                    "security_type": security_type,
                }
            )
        return rows

    @staticmethod
    def _classification_unavailable_warning(frame: pd.DataFrame) -> str:
        return "stock_classification_missing" if frame.empty else "stock_classification_empty"

    @staticmethod
    def _normalize_live_stock_master_response(
        payload: Mapping[str, Any],
    ) -> list[dict[str, str]]:
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("KRX stock master payload must contain a records list")

        rows: list[dict[str, str]] = []
        for item in records:
            if not isinstance(item, Mapping):
                continue
            stock_code = str(item.get("stock_code") or item.get("short_code") or "").strip()
            if not stock_code:
                continue
            rows.append(
                {
                    "stock_code": stock_code.zfill(6),
                    "stock_name": str(
                        item.get("stock_name") or item.get("isuAbwdNm") or ""
                    ).strip(),
                    "market": str(item.get("market") or item.get("mktNm") or "").strip(),
                    "security_type": str(
                        item.get("security_type") or item.get("security_group_type") or ""
                    ).strip(),
                    "listing_status": str(
                        item.get("listing_status") or item.get("listing_status_name") or "LISTED"
                    ).strip(),
                }
            )
        return rows
