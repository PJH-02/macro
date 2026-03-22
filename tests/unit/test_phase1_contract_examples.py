from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_provider_contract_examples_exist_for_each_provider_family() -> None:
    manifest = _load_json(MANIFEST_PATH)
    provider_families = manifest["provider_families"]

    assert isinstance(provider_families, list)
    assert {entry["provider"] for entry in provider_families} == {
        "krx",
        "dart",
        "ecos",
        "kosis",
        "us_macro",
    }

    for entry in provider_families:
        request_path = FIXTURE_ROOT / entry["request_fixture"]
        response_path = FIXTURE_ROOT / entry["response_fixture"]
        assert request_path.is_file(), request_path
        assert response_path.is_file(), response_path


def test_provider_contract_examples_match_manifest_keys() -> None:
    manifest = _load_json(MANIFEST_PATH)

    for entry in manifest["provider_families"]:
        request_payload = _load_json(FIXTURE_ROOT / entry["request_fixture"])
        response_payload = _load_json(FIXTURE_ROOT / entry["response_fixture"])

        assert set(entry["required_request_keys"]).issubset(request_payload)
        assert set(entry["required_response_keys"]).issubset(response_payload)
        assert request_payload["provider"] == entry["provider"]
        assert response_payload["provider"] == entry["provider"]


def test_krx_example_uses_auth_key_header() -> None:
    request_payload = _load_json(FIXTURE_ROOT / "krx" / "stock_master_request.json")

    assert request_payload["transport"]["headers"]["AUTH_KEY"] == "test-auth-key"


def test_dart_example_uses_monotone_cursor_fields() -> None:
    response_payload = _load_json(FIXTURE_ROOT / "dart" / "disclosure_list_response.json")

    assert set(response_payload["cursor"]) == {"rcept_dt", "rcept_no"}


def test_macro_examples_persist_release_metadata() -> None:
    ecos_payload = _load_json(FIXTURE_ROOT / "ecos" / "statistic_search_response.json")
    kosis_payload = _load_json(FIXTURE_ROOT / "kosis" / "statistical_data_response.json")
    us_payload = _load_json(FIXTURE_ROOT / "us_macro" / "fred_series_response.json")

    for payload in (ecos_payload, kosis_payload, us_payload):
        series = payload["series"]
        assert isinstance(series, list)
        assert series
        first = series[0]
        assert {"observation_date", "release_date", "retrieval_timestamp", "transformation_method"}.issubset(first)
