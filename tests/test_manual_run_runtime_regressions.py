from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from macro_screener.config import load_config
from macro_screener.data.dart_client import DARTClient, DARTDisclosureCursor
from macro_screener.db import SnapshotRegistry
from macro_screener.models import IndustryScore, RunType, Snapshot, SnapshotStatus, StockScore
from macro_screener.pipeline.publisher import publish_snapshot


def _snapshot_with_empty_block_scores() -> Snapshot:
    as_of = datetime.fromisoformat("2026-03-26T13:00:00+09:00")
    return Snapshot(
        run_id="runtime-regression",
        run_type=RunType.MANUAL,
        as_of_timestamp=as_of,
        input_cutoff=as_of,
        published_at=as_of,
        status=SnapshotStatus.INCOMPLETE,
        industry_scores=[
            IndustryScore(
                industry_code="IND",
                industry_name="Industry",
                base_score=1.0,
                overlay_adjustment=0.0,
                final_score=1.0,
                rank=1,
            )
        ],
        stock_scores=[
            StockScore(
                stock_code="000001",
                stock_name="Sample",
                industry_code="IND",
                final_score=0.0,
                rank=1,
                raw_dart_score=0.0,
                raw_industry_score=1.0,
                normalized_dart_score=0.0,
                normalized_industry_score=1.0,
                block_scores={},
            )
        ],
        warnings=[],
    )


def test_publish_snapshot_handles_empty_block_scores_for_parquet(tmp_path: Path) -> None:
    latest = publish_snapshot(
        _snapshot_with_empty_block_scores(),
        tmp_path,
        config=load_config(),
        store=SnapshotRegistry(tmp_path / "data" / "macro_screener.sqlite3"),
    )

    assert Path(latest["stock_parquet"]).exists()
    assert Path(latest["snapshot_json"]).exists()
    assert json.loads(Path(latest["snapshot_json"]).read_text(encoding="utf-8"))["run_id"] == (
        "runtime-regression"
    )


def test_dart_next_cursor_does_not_advance_to_cutoff_when_no_visible_disclosures() -> None:
    current = DARTDisclosureCursor(
        accepted_at="2026-03-25T18:00:00+09:00",
        input_cutoff="2026-03-25T18:00:00+09:00",
        rcept_dt="20260325",
        rcept_no="20260325000001",
    )

    next_cursor = DARTClient._next_cursor(
        [],
        input_cutoff=datetime.fromisoformat("2026-03-26T13:00:00+09:00"),
        current=current,
    )

    assert next_cursor == current


def test_dart_legacy_cutoff_cursor_does_not_filter_real_disclosures() -> None:
    legacy_cursor = DARTDisclosureCursor(
        accepted_at="2026-03-26T13:01:47.884026+09:00",
        input_cutoff="2026-03-26T13:01:47.884026+09:00",
    )
    disclosures = [
        {
            "accepted_at": "2026-03-25T18:00:00+09:00",
            "rcept_dt": "20260325",
            "rcept_no": "20260325000001",
            "stock_code": "000001",
            "title": "공시",
        }
    ]

    filtered = DARTClient._filter_items_after_cursor(disclosures, legacy_cursor)

    assert filtered == disclosures


def test_dart_fetch_live_disclosures_paginates_until_visible_items(monkeypatch: Any) -> None:
    class _Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> "_Response":
            return self

        def json(self) -> dict[str, object]:
            return self._payload

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def get(self, url: str, *, params: dict[str, str]) -> _Response:
            page_no = int(params["page_no"])
            if page_no == 1:
                return _Response(
                    {
                        "status": "000",
                        "total_page": 2,
                        "list": [
                            {
                                "stock_code": "000001",
                                "report_nm": "당일 공시",
                                "rcept_no": "20260326000001",
                                "rcept_dt": "20260326",
                            }
                        ],
                    }
                )
            return _Response(
                {
                    "status": "000",
                    "total_page": 2,
                    "list": [
                        {
                            "stock_code": "000002",
                            "report_nm": "전일 공시",
                            "rcept_no": "20260325000001",
                            "rcept_dt": "20260325",
                        }
                    ],
                }
            )

    monkeypatch.setattr("macro_screener.data.dart_client.httpx.Client", _Client)

    disclosures, next_cursor = DARTClient()._fetch_live_disclosures(
        api_key="token",
        input_cutoff=datetime.fromisoformat("2026-03-26T13:00:00+09:00"),
        cursor=None,
        retries=1,
    )

    assert len(disclosures) == 2
    assert [item["stock_code"] for item in disclosures] == ["000001", "000002"]
    assert next_cursor is not None
    assert next_cursor.rcept_no == "20260326000001"


def test_dart_same_day_items_become_visible_at_current_cutoff() -> None:
    accepted_at = DARTClient._accepted_at_for_live_item(
        "20260326",
        datetime.fromisoformat("2026-03-26T13:10:09+09:00"),
    )

    assert accepted_at == "2026-03-26T13:10:09+09:00"


def test_dart_watermark_start_date_uses_cutoff_for_legacy_or_missing_cursor() -> None:
    cutoff = datetime.fromisoformat("2026-03-26T13:10:09+09:00")
    legacy_cursor = DARTDisclosureCursor(
        accepted_at="2026-03-26T13:01:47.884026+09:00",
        input_cutoff="2026-03-26T13:01:47.884026+09:00",
    )

    assert DARTClient._watermark_start_date(None, cutoff) == cutoff
    assert DARTClient._watermark_start_date(legacy_cursor, cutoff) == cutoff
