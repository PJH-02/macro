from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _pytest.monkeypatch import MonkeyPatch

from macro_screener.data.krx_client import KRXClient
from macro_screener.data.reference import industry_code_slug

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts" / "krx"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_build_live_stock_master_request_matches_contract_fixture(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("KRX_API_KEY", "test-auth-key")

    client = KRXClient()
    expected = _load_json(FIXTURE_ROOT / "stock_master_request.json")

    assert client.build_live_stock_master_request(trading_date="20260320") == expected


def test_load_live_stocks_result_requires_fetcher_when_auth_key_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("KRX_API_KEY", "test-auth-key")
    monkeypatch.setattr(
        KRXClient,
        "_load_master_download_records",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("offline"))),
    )

    client = KRXClient(use_demo_fallback=False)
    result = client.load_live_stocks_result(trading_date="20260320")

    assert result.rows == []
    assert result.source == "unavailable"
    assert result.warnings == [
        "krx_live_fetcher_unconfigured",
        "krx_master_download_failed: offline",
    ]


def test_load_live_stocks_result_uses_master_download_when_fetcher_missing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    classification_path = tmp_path / "stock_classification.csv"
    classification_path.write_text(
        "\n".join(
            [
                "종목코드,종목명,대분류,중분류,소분류,종목구분",
                "005930,Samsung Electronics,제조,전기전자,반도체,보통주",
                "035420,NAVER,서비스,IT서비스,인터넷서비스,보통주",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    monkeypatch.setattr(
        KRXClient,
        "_load_master_download_records",
        staticmethod(
            lambda: [
                {
                    "stock_code": "005930",
                    "stock_name": "Samsung Electronics",
                    "market": "KOSPI",
                    "security_type": "COMMON",
                    "listing_status": "LISTED",
                },
                {
                    "stock_code": "035420",
                    "stock_name": "NAVER",
                    "market": "KOSDAQ",
                    "security_type": "COMMON",
                    "listing_status": "LISTED",
                },
            ]
        ),
    )

    client = KRXClient(stock_classification_path=classification_path, use_demo_fallback=False)
    result = client.load_live_stocks_result(trading_date="20260320")

    assert result.source == "live"
    assert result.rows == [
        {
            "stock_code": "005930",
            "stock_name": "Samsung Electronics",
            "industry_code": industry_code_slug(("제조", "전기전자", "반도체")),
        },
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "industry_code": industry_code_slug(("서비스", "IT서비스", "인터넷서비스")),
        },
    ]
    assert "krx_live_source_master_download" in result.warnings


def test_load_live_stocks_result_joins_live_rows_to_local_taxonomy(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    classification_path = tmp_path / "stock_classification.csv"
    classification_path.write_text(
        "\n".join(
            [
                "종목코드,종목명,대분류,중분류,소분류,종목구분",
                "005930,Samsung Electronics,제조,전기전자,반도체,보통주",
                "035420,NAVER,서비스,IT서비스,인터넷서비스,보통주",
                "091990,KODEX 200,금융,금융,ETF,ETF",
                "000660,SK Hynix,제조,전기전자,반도체,보통주",
            ]
        ),
        encoding="utf-8",
    )
    response_payload = _load_json(FIXTURE_ROOT / "stock_master_response.json")
    response_payload["records"] = [
        response_payload["records"][0],
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "market": "KOSPI",
            "security_type": "COMMON",
            "listing_status": "LISTED",
        },
        {
            "stock_code": "999999",
            "stock_name": "Unmapped Corp",
            "market": "KOSDAQ",
            "security_type": "COMMON",
            "listing_status": "LISTED",
        },
        {
            "stock_code": "091990",
            "stock_name": "KODEX 200",
            "market": "KOSPI",
            "security_type": "ETF",
            "listing_status": "LISTED",
        },
        {
            "stock_code": "000660",
            "stock_name": "SK Hynix",
            "market": "KOSPI",
            "security_type": "COMMON",
            "listing_status": "DELISTED",
        },
    ]
    monkeypatch.setenv("KRX_API_KEY", "test-auth-key")
    request_payloads: list[dict[str, Any]] = []

    def _fetcher(request_payload: dict[str, Any]) -> dict[str, Any]:
        request_payloads.append(request_payload)
        return response_payload

    client = KRXClient(
        stock_classification_path=classification_path,
        use_demo_fallback=False,
    )
    result = client.load_live_stocks_result(
        trading_date="20260320",
        fetcher=_fetcher,
    )

    assert request_payloads == [
        _load_json(FIXTURE_ROOT / "stock_master_request.json")
    ]
    assert result.source == "live"
    assert result.rows == [
        {
            "stock_code": "005930",
            "stock_name": "Samsung Electronics",
            "industry_code": industry_code_slug(("제조", "전기전자", "반도체")),
        },
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "industry_code": industry_code_slug(("서비스", "IT서비스", "인터넷서비스")),
        },
    ]
    assert result.warnings == ["krx_live_rows_missing_taxonomy_mapping=1"]
