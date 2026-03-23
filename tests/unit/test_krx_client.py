from __future__ import annotations

from pathlib import Path
from typing import Any

from macro_screener.data.krx_client import KRXClient
from macro_screener.data.reference import industry_code_slug


def test_build_live_stock_master_request_uses_env_and_trading_date(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("KRX_API_KEY", "test-auth-key")

    client = KRXClient()

    assert client.build_live_stock_master_request(trading_date="20260320") == {
        "provider": "krx",
        "service_family": "유가증권 종목기본정보",
        "transport": {
            "headers": {"AUTH_KEY": "test-auth-key"},
            "response_format": "json",
        },
        "params": {"basDd": "20260320"},
    }


def test_load_live_stocks_result_uses_master_download_when_fetcher_missing(
    tmp_path: Path,
    monkeypatch: Any,
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
    monkeypatch: Any,
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
    response_payload = {
        "provider": "krx",
        "service_family": "유가증권 종목기본정보",
        "records": [
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
        ],
    }
    monkeypatch.setenv("KRX_API_KEY", "test-auth-key")
    request_payloads: list[dict[str, Any]] = []

    def _fetcher(request_payload: dict[str, Any]) -> dict[str, Any]:
        request_payloads.append(request_payload)
        return response_payload

    client = KRXClient(stock_classification_path=classification_path, use_demo_fallback=False)
    result = client.load_live_stocks_result(trading_date="20260320", fetcher=_fetcher)

    assert request_payloads == [
        {
            "provider": "krx",
            "service_family": "유가증권 종목기본정보",
            "transport": {
                "headers": {"AUTH_KEY": "test-auth-key"},
                "response_format": "json",
            },
            "params": {"basDd": "20260320"},
        }
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
