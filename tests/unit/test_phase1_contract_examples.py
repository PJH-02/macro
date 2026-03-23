from __future__ import annotations

import json
from csv import DictReader
from pathlib import Path
from typing import Any

from macro_screener.data.reference import (
    build_industry_master_records,
    build_provisional_stage1_artifact,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
INDUSTRY_MASTER_PATH = REPO_ROOT / "data" / "reference" / "industry_master.csv"
STAGE1_ARTIFACT_PATH = REPO_ROOT / "config" / "stage1_sector_rank_tables.v1.json"
CLASSIFICATION_PATH = REPO_ROOT / "stock_classification.csv"


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
        required_keys = {
            "observation_date",
            "release_date",
            "retrieval_timestamp",
            "transformation_method",
        }
        assert required_keys.issubset(first)


def test_industry_master_is_materialized_from_stock_classification() -> None:
    assert INDUSTRY_MASTER_PATH.is_file()

    with INDUSTRY_MASTER_PATH.open("r", encoding="utf-8", newline="") as handle:
        committed_rows = list(DictReader(handle))

    assert committed_rows
    generated_at = committed_rows[0]["generated_at"]
    regenerated_rows = build_industry_master_records(
        CLASSIFICATION_PATH,
        generated_at=generated_at,
    )

    assert committed_rows == regenerated_rows
    assert {
        "industry_code",
        "industry_name",
        "sector_l1",
        "sector_l2",
        "sector_l3",
        "stock_count",
        "representative_stock_code",
        "source_classification_version",
        "generated_at",
    }.issubset(committed_rows[0])


def test_provisional_stage1_artifact_is_materialized_and_reproducible() -> None:
    artifact = _load_json(STAGE1_ARTIFACT_PATH)
    regenerated = build_provisional_stage1_artifact(
        INDUSTRY_MASTER_PATH,
        generated_at=str(artifact["generated_at"]),
    )

    assert artifact == regenerated
    assert artifact["artifact_status"] == "provisional"
    assert set(artifact["channel_weights"]) == {"G", "IC", "FC", "ED", "FX"}
    assert set(artifact["neutral_bands"]) == {"G", "IC", "FC", "ED", "FX"}
    for _channel, tables in artifact["sector_rank_tables"].items():
        assert set(tables) == {"pos", "neg"}
        assert len(tables["pos"]) == len(tables["neg"])
        assert len(set(tables["pos"])) == len(tables["pos"])
        assert len(set(tables["neg"])) == len(tables["neg"])
