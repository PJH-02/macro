from __future__ import annotations

import json
from pathlib import Path

from macro_screener.data.krx_client import KRXClient
from macro_screener.data.reference import industry_code_slug

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts" / "krx"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_build_live_stock_master_request_matches_contract_fixture() -> None:
    fixture = _load_json(FIXTURE_ROOT / "stock_master_request.json")

    request = KRXClient.build_live_stock_master_request(
        auth_key="test-auth-key",
        bas_dd="20260320",
    )

    assert request == fixture


def test_normalize_live_stock_master_response_joins_taxonomy_and_filters_non_common(
    tmp_path: Path,
) -> None:
    classification_path = tmp_path / "stock_classification.csv"
    classification_path.write_text(
        "\n".join(
            [
                "종목코드,종목명,대분류,중분류,소분류",
                "005930,삼성전자,제조,전자,반도체",
                "123456,샘플리츠,부동산,부동산,리츠",
            ]
        ),
        encoding="utf-8",
    )
    response = _load_json(FIXTURE_ROOT / "stock_master_response.json")
    response["records"] = [
        *list(response["records"]),  # type: ignore[index]
        {
            "stock_code": "123456",
            "stock_name": "샘플리츠",
            "market": "KOSPI",
            "security_type": "REIT",
            "listing_status": "LISTED",
        },
    ]

    client = KRXClient(stock_classification_path=classification_path)
    result = client.normalize_live_stock_master_response(response)

    assert result.source == "live"
    assert result.warnings == []
    assert result.rows == [
        {
            "stock_code": "005930",
            "stock_name": "Samsung Electronics",
            "industry_code": industry_code_slug(("제조", "전자", "반도체")),
        }
    ]


def test_normalize_live_stock_master_response_warns_on_missing_taxonomy(tmp_path: Path) -> None:
    classification_path = tmp_path / "stock_classification.csv"
    classification_path.write_text(
        "\n".join(
            [
                "종목코드,종목명,대분류,중분류,소분류",
                "005930,삼성전자,제조,전자,반도체",
            ]
        ),
        encoding="utf-8",
    )
    response = _load_json(FIXTURE_ROOT / "stock_master_response.json")
    response["records"] = [
        *list(response["records"]),  # type: ignore[index]
        {
            "stock_code": "000660",
            "stock_name": "SK hynix",
            "market": "KOSPI",
            "security_type": "COMMON",
            "listing_status": "LISTED",
        },
    ]

    client = KRXClient(stock_classification_path=classification_path)
    result = client.normalize_live_stock_master_response(response)

    assert result.rows == [
        {
            "stock_code": "005930",
            "stock_name": "Samsung Electronics",
            "industry_code": industry_code_slug(("제조", "전자", "반도체")),
        }
    ]
    assert result.warnings == ["krx_live_row_missing_taxonomy:000660"]
