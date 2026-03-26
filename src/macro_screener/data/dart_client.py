from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

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
class DARTDisclosureCursor:
    accepted_at: str
    input_cutoff: str
    rcept_dt: str | None = None
    rcept_no: str | None = None

    def to_dict(self) -> dict[str, str]:
        """객체를 직렬화 가능한 딕셔너리로 변환한다."""
        payload = {
            "accepted_at": self.accepted_at,
            "input_cutoff": self.input_cutoff,
        }
        if self.rcept_dt:
            payload["rcept_dt"] = self.rcept_dt
        if self.rcept_no:
            payload["rcept_no"] = self.rcept_no
        return payload

    def sort_key(self) -> tuple[str, str]:
        """정렬용 키를 반환한다."""
        return (self.accepted_at, self.rcept_no or "")


@dataclass(frozen=True, slots=True)
class DARTClient:
    disclosures_path: Path = Path("data/dart_disclosures.json")
    api_key_env: str = "DART_API_KEY"
    api_url: str = "https://opendart.fss.or.kr/api/list.json"
    timeout_seconds: float = 20.0
    use_demo_fallback: bool = True
    allow_local_file_inputs: bool = True

    def load_demo_disclosures(self) -> list[dict[str, Any]]:
        """데모 공시 데이터를 불러온다."""
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
        """공시 데이터를 불러온다."""
        cutoff = parse_datetime(input_cutoff)
        if self.disclosures_path.exists() and self.allow_local_file_inputs:
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
                existing_cursor_payload = (
                    store.get_watermark_payload(source_name="dart", resource_key="disclosures")
                    if store is not None
                    else None
                )
                existing_watermark = (
                    store.get_watermark(source_name="dart", resource_key="disclosures")
                    if store is not None
                    else None
                )
                existing_cursor_input = (
                    existing_cursor_payload
                    if existing_cursor_payload is not None
                    else existing_watermark
                )
                existing_cursor = self._coerce_cursor(existing_cursor_input)
                disclosures, next_cursor = self._fetch_live_disclosures(
                    api_key=api_key,
                    input_cutoff=cutoff,
                    cursor=existing_cursor,
                    retries=retries,
                )
                next_watermark = None if next_cursor is None else self._cursor_to_text(next_cursor)
                if store is not None and next_cursor is not None:
                    store.upsert_watermark_payload(
                        source_name="dart",
                        resource_key="disclosures",
                        payload=next_cursor.to_dict(),
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

        if not self.use_demo_fallback:
            raise RuntimeError(f"{self.api_key_env} is not configured")

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
        cursor: DARTDisclosureCursor | None,
        retries: int,
    ) -> tuple[list[dict[str, Any]], DARTDisclosureCursor | None]:
        """실시간 공시 데이터를 조회한다."""
        start_date = self._watermark_start_date(cursor, input_cutoff)
        params = {
            "crtfc_key": api_key,
            "bgn_de": start_date.strftime("%Y%m%d"),
            "end_de": input_cutoff.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "page_count": 100,
        }
        last_exc: Exception | None = None
        for _ in range(max(retries, 1)):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    total_pages = 1
                    page_no = 1
                    disclosures: list[dict[str, Any] | None] = []
                    current_key = None if cursor is None else cursor.sort_key()
                    while page_no <= total_pages:
                        payload = client.get(
                            self.api_url,
                            params={
                                **{key: str(value) for key, value in params.items()},
                                "page_no": str(page_no),
                            },
                        ).raise_for_status().json()
                        status = str(payload.get("status") or "000")
                        if status not in {"000", "013"}:
                            raise RuntimeError(
                                f"dart_api_status_error:{status}:{payload.get('message')}"
                            )
                        items = payload.get("list", [])
                        disclosures.extend(
                            self._normalize_live_item(item, input_cutoff) for item in items
                        )
                        if status == "013" or not items:
                            break
                        if (
                            current_key is not None
                            and cursor is not None
                            and not self._is_legacy_cutoff_cursor(cursor)
                        ):
                            page_visible = [
                                item
                                for item in disclosures[-len(items) :]
                                if item is not None
                            ]
                            if self._page_is_at_or_before_cursor(
                                page_visible,
                                current_key=current_key,
                                input_cutoff=input_cutoff,
                            ):
                                break
                        total_pages = max(int(payload.get("total_page") or 1), 1)
                        page_no += 1
                normalized = [item for item in disclosures if item is not None]
                visible = self._filter_visible_disclosures(normalized, input_cutoff)
                new_items = self._filter_items_after_cursor(visible, cursor)
                next_cursor = self._next_cursor(visible, input_cutoff=input_cutoff, current=cursor)
                return new_items, next_cursor
            except Exception as exc:  # pragma: no cover - exercised only with live calls
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        return [], cursor

    @staticmethod
    def _watermark_start_date(
        cursor: DARTDisclosureCursor | None,
        input_cutoff: datetime,
    ) -> datetime:
        """워터마크 기준 시작일을 계산한다."""
        if cursor is None or DARTClient._is_legacy_cutoff_cursor(cursor):
            return input_cutoff
        try:
            return min(parse_datetime(cursor.accepted_at), input_cutoff)
        except ValueError:
            return input_cutoff

    @staticmethod
    def _normalize_live_item(item: dict[str, Any], input_cutoff: datetime) -> dict[str, Any] | None:
        """실시간 공시 항목을 정규화한다."""
        stock_code = str(item.get("stock_code") or "").strip()
        if not stock_code:
            return None
        filed_date = str(item.get("rcept_dt") or "")
        receipt_no = str(item.get("rcept_no") or "").strip() or None
        accepted_at = DARTClient._accepted_at_for_live_item(filed_date, input_cutoff)
        elapsed_days = max((input_cutoff.date() - parse_datetime(accepted_at).date()).days, 0)
        return {
            "stock_code": stock_code.zfill(6),
            "event_code": None,
            "title": str(item.get("report_nm") or "").strip(),
            "trading_days_elapsed": elapsed_days,
            "accepted_at": accepted_at,
            "rcept_dt": filed_date or None,
            "rcept_no": receipt_no,
        }

    @staticmethod
    def _accepted_at_for_live_item(filed_date: str, input_cutoff: datetime) -> str:
        """공시 수리일을 현재 컷오프 기준 visible 시각으로 정규화한다."""
        if len(filed_date) != 8:
            return input_cutoff.isoformat()
        cutoff_date = input_cutoff.strftime("%Y%m%d")
        if filed_date == cutoff_date:
            return input_cutoff.isoformat()
        return f"{filed_date[:4]}-{filed_date[4:6]}-{filed_date[6:8]}T18:00:00+09:00"

    @staticmethod
    def _load_local_file(path: Path) -> list[dict[str, Any]]:
        """로컬 공시 파일을 불러온다."""
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
        """입력 시점 기준으로 공시를 거른다."""
        filtered: list[dict[str, Any]] = []
        for disclosure in disclosures:
            accepted_at = disclosure.get("accepted_at")
            if accepted_at is None:
                filtered.append(dict(disclosure))
                continue
            if parse_datetime(str(accepted_at)) <= cutoff:
                filtered.append(dict(disclosure))
        return filtered

    @classmethod
    def _filter_visible_disclosures(
        cls,
        disclosures: list[dict[str, Any]],
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """노출 가능한 공시만 남긴다."""
        return cls._filter_by_cutoff(disclosures, cutoff)

    @classmethod
    def _filter_items_after_cursor(
        cls,
        disclosures: list[dict[str, Any]],
        cursor: DARTDisclosureCursor | None,
    ) -> list[dict[str, Any]]:
        """커서 이후 공시만 남긴다."""
        if cursor is None:
            return [dict(item) for item in disclosures]
        if cls._is_legacy_cutoff_cursor(cursor):
            return [dict(item) for item in disclosures]
        filtered: list[dict[str, Any]] = []
        current_key = cursor.sort_key()
        for disclosure in disclosures:
            candidate_cursor = cls._cursor_from_disclosure(disclosure, cursor.input_cutoff)
            if candidate_cursor is None:
                filtered.append(dict(disclosure))
                continue
            if candidate_cursor.sort_key() > current_key:
                filtered.append(dict(disclosure))
        return filtered

    @classmethod
    def _next_cursor(
        cls,
        disclosures: list[dict[str, Any]],
        *,
        input_cutoff: datetime,
        current: DARTDisclosureCursor | None,
    ) -> DARTDisclosureCursor:
        """다음 커서를 계산한다."""
        if not disclosures:
            return current if current is not None else cls._cursor_for_cutoff(input_cutoff)
        cursor_candidates = []
        if current is not None and not cls._is_legacy_cutoff_cursor(current):
            cursor_candidates.append(current)
        for disclosure in disclosures:
            candidate = cls._cursor_from_disclosure(disclosure, input_cutoff.isoformat())
            if candidate is not None:
                cursor_candidates.append(candidate)
        return max(cursor_candidates, key=lambda item: item.sort_key())

    @staticmethod
    def _is_legacy_cutoff_cursor(cursor: DARTDisclosureCursor) -> bool:
        """수리번호/수리일이 없는 과거 cutoff-only cursor인지 판별한다."""
        return cursor.rcept_dt is None and cursor.rcept_no is None

    @classmethod
    def _page_is_at_or_before_cursor(
        cls,
        disclosures: list[dict[str, Any]],
        *,
        current_key: tuple[str, str],
        input_cutoff: datetime,
    ) -> bool:
        """현재 페이지가 이미 cursor 이하로 내려왔는지 판별한다."""
        cursors = [
            cls._cursor_from_disclosure(disclosure, input_cutoff.isoformat())
            for disclosure in disclosures
        ]
        materialized = [cursor for cursor in cursors if cursor is not None]
        if not materialized:
            return False
        return min(cursor.sort_key() for cursor in materialized) <= current_key

    @staticmethod
    def _cursor_for_cutoff(input_cutoff: datetime) -> DARTDisclosureCursor:
        """컷오프 기준 커서를 만든다."""
        cutoff_text = input_cutoff.isoformat()
        return DARTDisclosureCursor(accepted_at=cutoff_text, input_cutoff=cutoff_text)

    @staticmethod
    def _cursor_from_disclosure(
        disclosure: Mapping[str, Any],
        input_cutoff: str,
    ) -> DARTDisclosureCursor | None:
        """공시에서 커서를 만든다."""
        accepted_at = disclosure.get("accepted_at")
        if accepted_at is None:
            return None
        return DARTDisclosureCursor(
            accepted_at=str(accepted_at),
            input_cutoff=input_cutoff,
            rcept_dt=(
                str(disclosure["rcept_dt"])
                if disclosure.get("rcept_dt") not in (None, "")
                else None
            ),
            rcept_no=(
                str(disclosure["rcept_no"])
                if disclosure.get("rcept_no") not in (None, "")
                else None
            ),
        )

    @classmethod
    def _coerce_cursor(
        cls,
        value: Mapping[str, Any] | str | None,
    ) -> DARTDisclosureCursor | None:
        """입력값을 커서 객체로 정규화한다."""
        if value is None:
            return None
        if isinstance(value, Mapping):
            return cls._cursor_from_payload(value)
        text = value.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return cls._cursor_from_payload(payload)
        try:
            cutoff_text = parse_datetime(text).isoformat()
        except ValueError:
            return None
        return DARTDisclosureCursor(accepted_at=cutoff_text, input_cutoff=cutoff_text)

    @staticmethod
    def _cursor_from_payload(payload: Mapping[str, Any]) -> DARTDisclosureCursor | None:
        """페이로드에서 커서를 복원한다."""
        accepted_at = payload.get("accepted_at") or payload.get("input_cutoff")
        if accepted_at is None:
            return None
        input_cutoff = payload.get("input_cutoff") or accepted_at
        return DARTDisclosureCursor(
            accepted_at=str(accepted_at),
            input_cutoff=str(input_cutoff),
            rcept_dt=str(payload["rcept_dt"]) if payload.get("rcept_dt") is not None else None,
            rcept_no=str(payload["rcept_no"]) if payload.get("rcept_no") is not None else None,
        )

    @staticmethod
    def _cursor_to_text(cursor: DARTDisclosureCursor) -> str:
        """커서를 텍스트로 직렬화한다."""
        return json.dumps(cursor.to_dict(), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _write_cache(
        cache_path: Path,
        disclosures: list[dict[str, Any]],
        watermark: str | None,
        *,
        source: str,
    ) -> None:
        """공시 캐시를 기록한다."""
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
        """공시 캐시를 불러온다."""
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        disclosures = [dict(item) for item in payload.get("disclosures", [])]
        watermark = payload.get("watermark")
        return disclosures, None if watermark is None else str(watermark)
