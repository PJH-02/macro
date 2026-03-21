from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from macro_screener.db import SnapshotRegistry
from macro_screener.serialization import parse_datetime

DEFAULT_DISCLOSURES: list[dict[str, Any]] = [
    {
        "stock_code": "000270",
        "event_code": "B01",
        "title": "대규모 공급계약 체결",
        "trading_days_elapsed": 2,
        "accepted_at": "2026-03-19T18:00:00+09:00",
    },
    {
        "stock_code": "005380",
        "event_code": "N01",
        "title": "유상증자 결정",
        "trading_days_elapsed": 5,
        "accepted_at": "2026-03-16T18:00:00+09:00",
    },
    {
        "stock_code": "009540",
        "event_code": None,
        "title": "시설투자 결정",
        "trading_days_elapsed": 10,
        "accepted_at": "2026-03-11T18:00:00+09:00",
    },
    {
        "stock_code": "009540",
        "event_code": None,
        "title": "정정 공시",
        "trading_days_elapsed": 1,
        "accepted_at": "2026-03-20T18:00:00+09:00",
    },
    {
        "stock_code": "000100",
        "event_code": None,
        "title": "설명회 개최",
        "trading_days_elapsed": 0,
        "accepted_at": "2026-03-21T08:00:00+09:00",
    },
]


@dataclass(frozen=True, slots=True)
class DARTLoadResult:
    disclosures: list[dict[str, Any]]
    warnings: list[str]
    watermark: str | None = None
    source: str = "demo"


@dataclass(frozen=True, slots=True)
class DARTClient:
    disclosures_path: Path = Path("data/dart_disclosures.json")
    api_key_env: str = "DART_API_KEY"
    api_url: str = "https://opendart.fss.or.kr/api/list.json"
    timeout_seconds: float = 20.0
    use_demo_fallback: bool = True

    def load_demo_disclosures(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_DISCLOSURES]

    def load_disclosures(
        self,
        *,
        input_cutoff: str | datetime,
        retries: int,
        store: SnapshotRegistry | None = None,
        cache_path: Path | None = None,
        allow_stale: bool = True,
    ) -> DARTLoadResult:
        cutoff = parse_datetime(input_cutoff)
        if self.disclosures_path.exists():
            local_payload = self._load_local_file(self.disclosures_path)
            disclosures = self._filter_by_cutoff(local_payload, cutoff)
            watermark = cutoff.isoformat()
            if store is not None:
                store.upsert_watermark(
                    source_name="dart",
                    resource_key="disclosures",
                    watermark_value=watermark,
                )
            if cache_path is not None:
                self._write_cache(cache_path, disclosures, watermark, source="file")
            return DARTLoadResult(
                disclosures=disclosures,
                warnings=[],
                watermark=watermark,
                source="file",
            )

        api_key = os.getenv(self.api_key_env)
        if api_key:
            try:
                existing_watermark = (
                    store.get_watermark(source_name="dart", resource_key="disclosures")
                    if store
                    else None
                )
                disclosures, next_watermark = self._fetch_live_disclosures(
                    api_key=api_key,
                    input_cutoff=cutoff,
                    watermark=existing_watermark,
                    retries=retries,
                )
                if store is not None and next_watermark is not None:
                    store.upsert_watermark(
                        source_name="dart",
                        resource_key="disclosures",
                        watermark_value=next_watermark,
                    )
                if cache_path is not None:
                    self._write_cache(cache_path, disclosures, next_watermark, source="live")
                return DARTLoadResult(
                    disclosures=disclosures,
                    warnings=[],
                    watermark=next_watermark,
                    source="live",
                )
            except Exception as exc:  # pragma: no cover - live network path is best-effort
                if allow_stale and cache_path is not None and cache_path.exists():
                    disclosures, stale_watermark = self._load_cache(cache_path)
                    return DARTLoadResult(
                        disclosures=disclosures,
                        warnings=[f"dart_api_failed_using_stale_cache: {exc}"],
                        watermark=stale_watermark,
                        source="stale_cache",
                    )
                if not self.use_demo_fallback:
                    raise
                return DARTLoadResult(
                    disclosures=self.load_demo_disclosures(),
                    warnings=[f"dart_api_failed_using_demo_fallback: {exc}"],
                    watermark=cutoff.isoformat(),
                    source="demo",
                )

        warnings = (
            ["dart_source_unconfigured_using_demo_fallback"]
            if self.use_demo_fallback
            else []
        )
        disclosures = self.load_demo_disclosures() if self.use_demo_fallback else []
        if cache_path is not None and disclosures:
            self._write_cache(cache_path, disclosures, cutoff.isoformat(), source="demo")
        return DARTLoadResult(
            disclosures=self._filter_by_cutoff(disclosures, cutoff),
            warnings=warnings,
            watermark=cutoff.isoformat(),
            source="demo",
        )

    def _fetch_live_disclosures(
        self,
        *,
        api_key: str,
        input_cutoff: datetime,
        watermark: str | None,
        retries: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        start_date = self._watermark_start_date(watermark, input_cutoff)
        params = {
            "crtfc_key": api_key,
            "bgn_de": start_date.strftime("%Y%m%d"),
            "end_de": input_cutoff.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "page_no": 1,
            "page_count": 100,
        }
        last_exc: Exception | None = None
        for _ in range(max(retries, 1)):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    payload = client.get(
                        self.api_url,
                        params={key: str(value) for key, value in params.items()},
                    ).raise_for_status().json()
                items = payload.get("list", [])
                disclosures = [self._normalize_live_item(item, input_cutoff) for item in items]
                normalized = [item for item in disclosures if item is not None]
                next_watermark = payload.get("page_no") or input_cutoff.isoformat()
                return normalized, str(next_watermark)
            except Exception as exc:  # pragma: no cover - exercised only with live calls
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        return [], watermark

    @staticmethod
    def _watermark_start_date(watermark: str | None, input_cutoff: datetime) -> datetime:
        if watermark is None:
            return input_cutoff - timedelta(days=30)
        try:
            return parse_datetime(watermark)
        except ValueError:
            return input_cutoff - timedelta(days=30)

    @staticmethod
    def _normalize_live_item(item: dict[str, Any], input_cutoff: datetime) -> dict[str, Any] | None:
        stock_code = str(item.get("stock_code") or "").strip()
        if not stock_code:
            return None
        filed_date = str(item.get("rcept_dt") or "")
        if len(filed_date) == 8:
            accepted_at = f"{filed_date[:4]}-{filed_date[4:6]}-{filed_date[6:8]}T18:00:00+09:00"
        else:
            accepted_at = input_cutoff.isoformat()
        elapsed_days = max((input_cutoff.date() - parse_datetime(accepted_at).date()).days, 0)
        return {
            "stock_code": stock_code.zfill(6),
            "event_code": None,
            "title": str(item.get("report_nm") or "").strip(),
            "trading_days_elapsed": elapsed_days,
            "accepted_at": accepted_at,
        }

    @staticmethod
    def _load_local_file(path: Path) -> list[dict[str, Any]]:
        if path.suffix.lower() == ".jsonl":
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("DART disclosures file must contain a top-level list")
        return [dict(item) for item in payload]

    @staticmethod
    def _filter_by_cutoff(
        disclosures: list[dict[str, Any]], cutoff: datetime
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for disclosure in disclosures:
            accepted_at = disclosure.get("accepted_at")
            if accepted_at is None:
                filtered.append(dict(disclosure))
                continue
            if parse_datetime(str(accepted_at)) <= cutoff:
                filtered.append(dict(disclosure))
        return filtered

    @staticmethod
    def _write_cache(
        cache_path: Path,
        disclosures: list[dict[str, Any]],
        watermark: str | None,
        *,
        source: str,
    ) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {"source": source, "watermark": watermark, "disclosures": disclosures},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _load_cache(cache_path: Path) -> tuple[list[dict[str, Any]], str | None]:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        disclosures = [dict(item) for item in payload.get("disclosures", [])]
        watermark = payload.get("watermark")
        return disclosures, None if watermark is None else str(watermark)
