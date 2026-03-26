from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")

STOCK_CODE_SECTOR_OVERRIDES: dict[str, str] = {
    "0088M0": "헬스케어/바이오",  # 메쥬
    "408470": "소프트웨어/인터넷/게임",  # 한패스
}
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.data.reference import (
    GROUPED_SECTOR_EXPOSURE_MATRIX,
    grouped_sector_code,
    industry_code_slug,
    map_classification_row_to_grouped_sector,
)

DEFAULT_EXPOSURES: list[dict[str, Any]] = [
    {"industry_code": grouped_sector_code(sector), "industry_name": sector, "exposures": {channel: float(GROUPED_SECTOR_EXPOSURE_MATRIX[channel][sector]) for channel in GROUPED_SECTOR_EXPOSURE_MATRIX}}
    for sector in sorted({sector for matrix in GROUPED_SECTOR_EXPOSURE_MATRIX.values() for sector in matrix})
]

DEFAULT_STOCKS: list[dict[str, Any]] = [
    {"stock_code": "000270", "stock_name": "Kia", "industry_code": grouped_sector_code("자동차/부품"), "industry_name": "자동차/부품"},
    {"stock_code": "005380", "stock_name": "Hyundai Motor", "industry_code": grouped_sector_code("자동차/부품"), "industry_name": "자동차/부품"},
    {"stock_code": "009540", "stock_name": "HD Korea Shipbuilding", "industry_code": grouped_sector_code("조선"), "industry_name": "조선"},
    {"stock_code": "000100", "stock_name": "Yuhan", "industry_code": grouped_sector_code("헬스케어/바이오"), "industry_name": "헬스케어/바이오"},
]

NON_COMMON_STOCK_KEYWORDS = ("ETF", "ETN", "REIT", "리츠", "SPAC", "스팩")
DEFAULT_ALLOWED_MARKETS: tuple[str, ...] = ("KOSPI", "KOSDAQ")
LIVE_STOCK_MASTER_SERVICE_FAMILY = "유가증권 종목기본정보"


@dataclass(frozen=True, slots=True)
class KRXLoadResult:
    rows: list[dict[str, Any]]
    source: str
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class KRXClient:
    stock_classification_path: Path | None = None
    exposure_matrix_path: Path = Path("config/macro_sector_exposure.v2.json")
    ohlcv_path: Path = Path("data/ohlcv.csv")
    api_key_env: str = "KRX_API_KEY"
    use_demo_fallback: bool = True
    allowed_markets: tuple[str, ...] = DEFAULT_ALLOWED_MARKETS

    def build_live_stock_master_request(
        self,
        *,
        auth_key: str | None = None,
        bas_dd: str | None = None,
        trading_date: str | None = None,
    ) -> dict[str, Any]:
        """실시간 종목 마스터 요청을 구성한다."""
        raw_auth_key = auth_key if auth_key is not None else os.getenv(self.api_key_env)
        resolved_auth_key = "" if raw_auth_key is None else raw_auth_key.strip()
        if not resolved_auth_key:
            raise ValueError(f"Missing KRX auth key env: {self.api_key_env}")
        resolved_bas_dd = (bas_dd or trading_date or "").strip()
        if not resolved_bas_dd:
            raise ValueError("Missing KRX trading_date/bas_dd")
        return {
            "provider": "krx",
            "service_family": LIVE_STOCK_MASTER_SERVICE_FAMILY,
            "transport": {
                "headers": {"AUTH_KEY": resolved_auth_key},
                "response_format": "json",
            },
            "params": {"basDd": resolved_bas_dd},
        }

    def load_demo_exposures(self) -> list[dict[str, Any]]:
        """데모 노출도 데이터를 불러온다."""
        return [dict(item) for item in DEFAULT_EXPOSURES]

    def load_demo_stocks(self) -> list[dict[str, Any]]:
        """데모 종목 데이터를 불러온다."""
        return [dict(item) for item in DEFAULT_STOCKS]

    def load_exposures(self) -> list[dict[str, Any]]:
        """노출도 목록을 불러온다."""
        return self.load_exposures_result().rows

    def load_exposures_result(self) -> KRXLoadResult:
        """노출도 로드 결과를 불러온다."""
        if not self.exposure_matrix_path.exists():
            return KRXLoadResult(rows=[], source="unavailable", warnings=["krx_exposure_matrix_missing"])
        payload = json.loads(self.exposure_matrix_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("sector_exposure"), dict):
            return KRXLoadResult(rows=[], source="unavailable", warnings=["krx_exposure_matrix_invalid"])
        matrix = {
            str(channel): {str(sector): int(value) for sector, value in sectors.items()}
            for channel, sectors in payload["sector_exposure"].items()
            if isinstance(sectors, dict)
        }
        if set(matrix) != set(CHANNELS):
            return KRXLoadResult(rows=[], source="unavailable", warnings=["krx_exposure_matrix_incomplete_channels"])
        sectors = sorted({sector for channel_map in matrix.values() for sector in channel_map})
        expected = sorted({sector for channel_map in GROUPED_SECTOR_EXPOSURE_MATRIX.values() for sector in channel_map})
        if sectors != expected:
            return KRXLoadResult(rows=[], source="unavailable", warnings=["krx_exposure_matrix_incomplete_sectors"])
        rows = [
            {
                "industry_code": grouped_sector_code(sector),
                "industry_name": sector,
                "exposures": {channel: float(matrix[channel][sector]) for channel in CHANNELS},
            }
            for sector in sectors
        ]
        return KRXLoadResult(rows=rows, source="file", warnings=[])

    def load_stock_classification(self) -> pd.DataFrame:
        """종목 분류표를 불러온다."""
        if self.stock_classification_path is None or not self.stock_classification_path.exists():
            return pd.DataFrame(columns=["종목코드", "종목명", "대분류", "중분류", "소분류"])
        return pd.read_csv(self.stock_classification_path, dtype=str).fillna("")

    def load_live_stocks_result(
        self,
        *,
        trading_date: str,
        fetcher: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> KRXLoadResult:
        """실시간 종목 로드 결과를 불러온다."""
        auth_key = os.getenv(self.api_key_env, "").strip()
        if fetcher is None:
            return self._load_live_stocks_without_fetcher(auth_key=auth_key)
        if not auth_key:
            return self._unavailable_live_result("krx_live_source_unconfigured")
        try:
            request_payload = self.build_live_stock_master_request(
                auth_key=auth_key,
                bas_dd=trading_date,
            )
            live_rows = self._normalize_live_stock_master_response(fetcher(request_payload))
        except Exception as exc:
            return self._unavailable_live_result(f"krx_live_fetch_failed: {exc}")
        if not live_rows:
            return self._unavailable_live_result("krx_live_records_empty")

        return self.normalize_live_stock_records(live_rows)

    def _load_live_stocks_without_fetcher(self, *, auth_key: str) -> KRXLoadResult:
        """명시적 fetcher 없이 실시간 종목 결과를 불러온다."""
        try:
            return self._load_live_stocks_via_master_download()
        except Exception as exc:
            warning_prefix = (
                "krx_live_source_unconfigured"
                if not auth_key
                else "krx_live_fetcher_unconfigured"
            )
            return self._unavailable_live_result(
                warning_prefix,
                f"krx_master_download_failed: {exc}",
            )

    @staticmethod
    def _unavailable_live_result(*warnings: str) -> KRXLoadResult:
        """실시간 종목 경로의 실패 결과를 만든다."""
        return KRXLoadResult(rows=[], source="unavailable", warnings=list(warnings))

    def normalize_live_stock_records(self, live_rows: Sequence[Mapping[str, Any]]) -> KRXLoadResult:
        """실시간 종목 레코드를 분류표 기준으로 정규화한다."""
        frame = self.load_stock_classification()
        taxonomy_rows = self._classification_rows(frame, include_non_common=True)
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
                override_sector = STOCK_CODE_SECTOR_OVERRIDES.get(stock_code)
                if override_sector is None:
                    missing_taxonomy += 1
                    continue
                taxonomy_row = {
                    "industry_code": grouped_sector_code(override_sector),
                    "industry_name": override_sector,
                }
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
                    "industry_name": str(taxonomy_row.get("industry_name") or taxonomy_row["industry_code"]),
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

    def _load_live_stocks_via_master_download(self) -> KRXLoadResult:
        """마스터 다운로드 경로로 실시간 종목을 불러온다."""
        live_result = self.normalize_live_stock_records(self._load_master_download_records())
        warnings = [*live_result.warnings, "krx_live_source_master_download"]
        if live_result.rows:
            return KRXLoadResult(rows=live_result.rows, source="live", warnings=warnings)
        return KRXLoadResult(
            rows=[],
            source="unavailable",
            warnings=warnings or ["krx_master_download_empty"],
        )

    def load_stocks(self) -> list[dict[str, Any]]:
        """종목 목록을 불러온다."""
        return self.load_stocks_result().rows

    def load_stocks_result(self) -> KRXLoadResult:
        """종목 로드 결과를 불러온다."""
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
                "industry_name": str(row.get("industry_name") or row["industry_code"]),
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
        """OHLCV 데이터를 불러온다."""
        if not self.ohlcv_path.exists():
            return pd.DataFrame(
                columns=["stock_code", "trading_date", "open", "high", "low", "close", "volume"]
            )
        return pd.read_csv(self.ohlcv_path)

    @staticmethod
    def _first_value(row: pd.Series, *columns: str) -> str:
        """후보 컬럼에서 첫 값을 선택한다."""
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
        """보통주가 아닌 종목인지 판단한다."""
        upper_name = stock_name.upper()
        upper_type = security_type.upper()
        return any(
            keyword in upper_name or keyword in upper_type
            for keyword in NON_COMMON_STOCK_KEYWORDS
        )

    def _classification_rows(
        self,
        frame: pd.DataFrame,
        *,
        include_non_common: bool = False,
    ) -> list[dict[str, str]]:
        """분류표를 종목 행 목록으로 정리한다."""
        rows: list[dict[str, str]] = []
        for _, row in frame.iterrows():
            stock_code = self._first_value(row, "stock_code", "종목코드", "code")
            stock_name = self._first_value(row, "stock_name", "종목명", "name")
            sector_l1 = self._first_value(row, "sector_l1", "대분류")
            sector_l2 = self._first_value(row, "sector_l2", "중분류")
            sector_l3 = self._first_value(row, "sector_l3", "소분류")
            grouped_sector = map_classification_row_to_grouped_sector({
                "소분류": sector_l3,
                "sector_l3": sector_l3,
            })
            security_type = self._first_value(row, "security_type", "증권구분", "종목구분")
            if not stock_code or not stock_name:
                continue
            if not grouped_sector:
                raise ValueError(f"unmapped_grouped_sector:{stock_code}:{sector_l1}/{sector_l2}/{sector_l3}")
            industry_code = grouped_sector_code(grouped_sector)
            if (
                not include_non_common
                and self._is_non_common_equity(stock_name=stock_name, security_type=security_type)
            ):
                continue
            rows.append(
                {
                    "stock_code": stock_code.zfill(6),
                    "stock_name": stock_name,
                    "industry_code": industry_code,
                    "industry_name": grouped_sector,
                    "security_type": security_type,
                }
            )
        return rows

    @staticmethod
    def _classification_unavailable_warning(frame: pd.DataFrame) -> str:
        """분류표 부재 경고 코드를 반환한다."""
        return "stock_classification_missing" if frame.empty else "stock_classification_empty"

    @staticmethod
    def _load_kis_security_module() -> Any:
        """KIS 보안 모듈을 동적으로 불러온다."""
        module_path = Path(__file__).resolve().parents[2] / "security" / "kis_security_defended.py"
        spec = importlib.util.spec_from_file_location("kis_security_defended_runtime", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load KIS security module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _load_master_download_records() -> list[dict[str, str]]:
        """마스터 다운로드 종목 레코드를 불러온다."""
        module = KRXClient._load_kis_security_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            kospi = module.load_kospi_master(workdir)
            kosdaq = module.load_kosdaq_master(workdir)
            combined = module.pd.concat([kospi, kosdaq], ignore_index=True)
            common = combined[
                combined.apply(lambda row: module.classify_security(row)[0] == "보통주", axis=1)
            ].copy()
            records: list[dict[str, str]] = []
            for _, row in common.iterrows():
                records.append(
                    {
                        "stock_code": str(row.get("종목코드") or "").zfill(6),
                        "stock_name": str(row.get("종목명") or "").strip(),
                        "market": str(row.get("시장") or "").strip().upper(),
                        "security_type": "COMMON",
                        "listing_status": "LISTED",
                    }
                )
            return records

    @staticmethod
    def _normalize_live_stock_master_response(
        payload: Mapping[str, Any],
    ) -> list[dict[str, str]]:
        """실시간 종목 마스터 응답을 레코드 목록으로 정규화한다."""
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
