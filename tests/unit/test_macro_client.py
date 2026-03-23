from __future__ import annotations

from datetime import datetime
from typing import Any

from macro_screener.data import macro_client


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_load_live_macro_data_source_builds_fixed_roster_payloads(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    monkeypatch.setattr(macro_client, "_require_api_key", lambda env_name: f"{env_name}-token")
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_yoy_3mma",
        lambda **kwargs: (1.25, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_credit_spread_z36",
        lambda **kwargs: (-0.5, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_log_return_3m",
        lambda **kwargs: (2.5, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_yoy_3mma",
        lambda **kwargs: (0.75, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_zscore36",
        lambda **kwargs: (-0.25, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_yoy_3obs_mean",
        lambda **kwargs: (1.5, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_log_return_3m",
        lambda **kwargs: (-1.25, _dt("2026-03-01T00:00:00+00:00")),
    )

    def _capture(series_payloads: dict[str, dict[str, Any]], **kwargs: Any) -> object:
        captured["series_payloads"] = series_payloads
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(
        macro_client,
        "build_live_macro_data_source_from_provider_payloads",
        _capture,
    )
    monkeypatch.setattr(
        macro_client,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {
                "now": staticmethod(lambda tz=None: _dt("2026-03-23T06:00:00+00:00")),
            },
        ),
    )

    result = macro_client.load_live_macro_data_source(
        as_of_timestamp="2026-03-20T00:00:00+00:00",
        input_cutoff="2026-03-21T00:00:00+00:00",
        source_name="ecos_fred_live",
        source_version="cleanup-test",
    )

    assert result is sentinel
    assert set(captured["series_payloads"]) == {
        "kr_ipi_yoy_3mma",
        "kr_cpi_yoy_3mma",
        "kr_exports_us_yoy_3mma",
        "kr_credit_spread_z36",
        "usdkrw_3m_log_return",
        "us_ipi_yoy_3mma",
        "us_cpi_yoy_3mma",
        "us_credit_spread_z36",
        "us_real_imports_goods_yoy_3mma",
        "broad_usd_3m_log_return",
    }
    assert captured["series_payloads"]["kr_ipi_yoy_3mma"]["provider"] == "ecos"
    assert (
        captured["series_payloads"]["broad_usd_3m_log_return"]["series"][0]["series_id"]
        == "TWEXBGSMTH"
    )
    assert captured["kwargs"] == {
        "degraded_mode": False,
        "source_name": "ecos_fred_live",
        "source_version": "cleanup-test",
        "confidence_by_series": {},
        "warning_flags_by_series": {},
    }


def test_load_live_macro_data_source_uses_degraded_ed_fallback_when_imports_fail(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(macro_client, "_require_api_key", lambda env_name: f"{env_name}-token")
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_yoy_3mma",
        lambda **kwargs: (1.25, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_credit_spread_z36",
        lambda **kwargs: (-0.5, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_ecos_log_return_3m",
        lambda **kwargs: (2.5, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_zscore36",
        lambda **kwargs: (-0.25, _dt("2026-03-01T00:00:00+00:00")),
    )
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_log_return_3m",
        lambda **kwargs: (-1.25, _dt("2026-03-01T00:00:00+00:00")),
    )

    def _fred_yoy(**kwargs: Any) -> tuple[float, datetime]:
        if kwargs["source_series_id"] == "DGDSRX1":
            return 0.9, _dt("2026-03-01T00:00:00+00:00")
        return 0.75, _dt("2026-03-01T00:00:00+00:00")

    monkeypatch.setattr(macro_client, "_compute_fred_yoy_3mma", _fred_yoy)
    monkeypatch.setattr(
        macro_client,
        "_compute_fred_yoy_3obs_mean",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("imports unavailable")),
    )
    monkeypatch.setattr(
        macro_client,
        "build_live_macro_data_source_from_provider_payloads",
        lambda series_payloads, **kwargs: captured.update(
            {"series_payloads": series_payloads, "kwargs": kwargs}
        ),
    )
    monkeypatch.setattr(
        macro_client,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {
                "now": staticmethod(lambda tz=None: _dt("2026-03-23T06:00:00+00:00")),
            },
        ),
    )

    macro_client.load_live_macro_data_source(
        as_of_timestamp="2026-03-20T00:00:00+00:00",
        input_cutoff="2026-03-21T00:00:00+00:00",
    )

    assert "us_real_imports_goods_yoy_3mma" not in captured["series_payloads"]
    assert "us_real_pce_goods_yoy_3mma" in captured["series_payloads"]
    assert captured["kwargs"]["degraded_mode"] is True
    assert captured["kwargs"]["confidence_by_series"] == {"us_real_pce_goods_yoy_3mma": 0.6}
    assert captured["kwargs"]["warning_flags_by_series"] == {
        "us_real_pce_goods_yoy_3mma": (
            "us_real_imports_goods_live_fetch_failed:ValueError",
        )
    }
