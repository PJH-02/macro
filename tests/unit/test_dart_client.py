from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from macro_screener.config import load_config
from macro_screener.data.dart_client import DARTClient
from macro_screener.db import SnapshotRegistry


class _DummyResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> "_DummyResponse":
        return self

    def json(self) -> dict[str, Any]:
        return self._payload


class _DummyClient:
    def __init__(self, *, payload: dict[str, Any], captured_params: list[dict[str, str]]) -> None:
        self._payload = payload
        self._captured_params = captured_params

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        return False

    def get(self, _url: str, *, params: dict[str, str]) -> _DummyResponse:
        self._captured_params.append(dict(params))
        return _DummyResponse(self._payload)


def _build_registry(tmp_path: Path) -> SnapshotRegistry:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "default.yaml").write_text("{}", encoding="utf-8")
    config = load_config(config_dir / "default.yaml")
    registry = SnapshotRegistry.for_config(config=config, base_path=tmp_path)
    registry.initialize()
    return registry


def test_live_disclosures_persist_structured_cursor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = _build_registry(tmp_path)
    captured_params: list[dict[str, str]] = []
    payload = {
        "page_no": 7,
        "list": [
            {
                "stock_code": "005930",
                "report_nm": "공급계약 체결",
                "rcept_dt": "20260320",
                "rcept_no": "202603200001",
            },
            {
                "stock_code": "000270",
                "report_nm": "시설투자 결정",
                "rcept_dt": "20260321",
                "rcept_no": "202603210001",
            },
        ],
    }

    def _client_factory(*args: Any, **kwargs: Any) -> _DummyClient:
        del args, kwargs
        return _DummyClient(payload=payload, captured_params=captured_params)

    monkeypatch.setattr("macro_screener.data.dart_client.httpx.Client", _client_factory)
    monkeypatch.setenv("DART_API_KEY", "test-key")

    result = DARTClient(use_demo_fallback=False).load_disclosures(
        input_cutoff="2026-03-21T18:00:00+09:00",
        retries=1,
        store=registry,
    )

    persisted_cursor = registry.get_watermark_payload(
        source_name="dart",
        resource_key="disclosures",
    )

    assert result.source == "live"
    assert len(result.disclosures) == 2
    assert captured_params[0]["bgn_de"] == "20260219"
    assert persisted_cursor == {
        "accepted_at": "2026-03-21T18:00:00+09:00",
        "input_cutoff": "2026-03-21T18:00:00+09:00",
        "rcept_dt": "20260321",
        "rcept_no": "202603210001",
    }
    assert registry.get_watermark(source_name="dart", resource_key="disclosures") != "7"


def test_live_disclosures_filter_duplicates_at_or_before_cursor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = _build_registry(tmp_path)
    registry.upsert_watermark_payload(
        source_name="dart",
        resource_key="disclosures",
        payload={
            "accepted_at": "2026-03-20T18:00:00+09:00",
            "input_cutoff": "2026-03-20T18:00:00+09:00",
            "rcept_dt": "20260320",
            "rcept_no": "202603200001",
        },
    )
    captured_params: list[dict[str, str]] = []
    payload = {
        "page_no": 1,
        "list": [
            {
                "stock_code": "005930",
                "report_nm": "공급계약 체결",
                "rcept_dt": "20260320",
                "rcept_no": "202603200001",
            },
            {
                "stock_code": "000270",
                "report_nm": "시설투자 결정",
                "rcept_dt": "20260320",
                "rcept_no": "202603200002",
            },
            {
                "stock_code": "035420",
                "report_nm": "유상증자 결정",
                "rcept_dt": "20260321",
                "rcept_no": "202603210001",
            },
        ],
    }

    def _client_factory(*args: Any, **kwargs: Any) -> _DummyClient:
        del args, kwargs
        return _DummyClient(payload=payload, captured_params=captured_params)

    monkeypatch.setattr("macro_screener.data.dart_client.httpx.Client", _client_factory)
    monkeypatch.setenv("DART_API_KEY", "test-key")

    result = DARTClient(use_demo_fallback=False).load_disclosures(
        input_cutoff=datetime.fromisoformat("2026-03-21T18:00:00+09:00"),
        retries=1,
        store=registry,
    )

    assert captured_params[0]["bgn_de"] == "20260320"
    assert [item["stock_code"] for item in result.disclosures] == ["000270", "035420"]

    persisted_cursor = registry.get_watermark_payload(
        source_name="dart",
        resource_key="disclosures",
    )
    assert persisted_cursor == {
        "accepted_at": "2026-03-21T18:00:00+09:00",
        "input_cutoff": "2026-03-21T18:00:00+09:00",
        "rcept_dt": "20260321",
        "rcept_no": "202603210001",
    }


def test_missing_api_key_raises_when_demo_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DART_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DART_API_KEY"):
        DARTClient(
            disclosures_path=tmp_path / "dart_disclosures.json",
            use_demo_fallback=False,
            allow_local_file_inputs=False,
        ).load_disclosures(
            input_cutoff="2026-03-21T18:00:00+09:00",
            retries=1,
        )


def test_local_file_is_ignored_when_live_mode_disallows_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    disclosures_path = tmp_path / "dart_disclosures.json"
    disclosures_path.write_text(
        '[{"stock_code":"111111","title":"local file disclosure","accepted_at":"2026-03-21T09:00:00+09:00"}]',
        encoding="utf-8",
    )
    captured_params: list[dict[str, str]] = []
    payload = {
        "page_no": 1,
        "list": [
            {
                "stock_code": "005930",
                "report_nm": "공급계약 체결",
                "rcept_dt": "20260321",
                "rcept_no": "202603210001",
            }
        ],
    }

    def _client_factory(*args: Any, **kwargs: Any) -> _DummyClient:
        del args, kwargs
        return _DummyClient(payload=payload, captured_params=captured_params)

    monkeypatch.setattr("macro_screener.data.dart_client.httpx.Client", _client_factory)
    monkeypatch.setenv("DART_API_KEY", "test-key")

    result = DARTClient(
        disclosures_path=disclosures_path,
        use_demo_fallback=False,
        allow_local_file_inputs=False,
    ).load_disclosures(
        input_cutoff="2026-03-21T18:00:00+09:00",
        retries=1,
    )

    assert captured_params[0]["bgn_de"] == "20260219"
    assert result.source == "live"
    assert [item["stock_code"] for item in result.disclosures] == ["005930"]
