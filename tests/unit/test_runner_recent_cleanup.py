from __future__ import annotations

from dataclasses import replace
from typing import Any

from macro_screener.config import load_config
from macro_screener.data.macro_client import MacroLoadResult
from macro_screener.models import RunMode
from macro_screener.pipeline import runner


def _channel_states() -> dict[str, int]:
    return {"G": 1, "IC": 0, "FC": -1, "ED": 1, "FX": 0}


def test_resolve_macro_states_uses_live_loader_in_production_live_mode(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    config = load_config(None)
    config = replace(
        config,
        environment="production",
        runtime=replace(
            config.runtime,
            normal_mode="live",
            reuse_last_known_channel_states=True,
        ),
    )
    expected = MacroLoadResult(channel_states=_channel_states(), source_name="ecos_fred_live")

    class _LiveSource:
        def fetch_channel_states(self) -> MacroLoadResult:
            return expected

    def _fake_live_loader(**kwargs: Any) -> _LiveSource:
        captured.update(kwargs)
        return _LiveSource()

    monkeypatch.setattr(runner, "load_live_macro_data_source", _fake_live_loader)

    result = runner._resolve_macro_states(
        config=config,
        store=object(),
        context={
            "as_of_timestamp": "2026-03-20T08:30:00+09:00",
            "input_cutoff": "2026-03-19T18:00:00+09:00",
        },
        mode=RunMode.MANUAL,
        channel_states=None,
        use_demo_inputs=False,
    )

    assert result is expected
    assert captured == {
        "as_of_timestamp": "2026-03-20T08:30:00+09:00",
        "input_cutoff": "2026-03-19T18:00:00+09:00",
        "ecos_api_key_env": config.runtime.ecos_api_key_env,
        "fred_api_key_env": config.runtime.fred_api_key_env,
        "source_name": "ecos_fred_live",
        "source_version": config.config_version,
    }


def test_resolve_macro_states_falls_back_to_persisted_states_after_live_loader_error(
    monkeypatch: Any,
) -> None:
    config = load_config(None)
    config = replace(
        config,
        environment="production",
        runtime=replace(
            config.runtime,
            normal_mode="live",
            reuse_last_known_channel_states=True,
        ),
    )
    expected = MacroLoadResult(
        channel_states=_channel_states(),
        source_name="persisted",
        fallback_mode="last_known_channel_states",
    )

    class _PersistedSource:
        def __init__(self, store: object) -> None:
            self.store = store

        def fetch_channel_states(self) -> MacroLoadResult:
            return expected

    monkeypatch.setattr(
        runner,
        "load_live_macro_data_source",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("live unavailable")),
    )
    monkeypatch.setattr(runner, "PersistedMacroDataSource", _PersistedSource)

    result = runner._resolve_macro_states(
        config=config,
        store=object(),
        context={
            "as_of_timestamp": "2026-03-20T08:30:00+09:00",
            "input_cutoff": "2026-03-19T18:00:00+09:00",
        },
        mode=RunMode.MANUAL,
        channel_states=None,
        use_demo_inputs=False,
    )

    assert result is expected
