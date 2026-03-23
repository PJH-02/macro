from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from macro_screener.data.macro_client import (
    FIXED_CHANNEL_SERIES_ROSTER,
    FIXED_SERIES_CLASSIFIER_SPECS,
    LiveMacroDataSource,
    MacroSeriesSignal,
    build_ecos_request_contract,
    build_fixed_channel_signal_map,
    build_fred_request_contract,
    build_kosis_request_contract,
    build_live_macro_data_source_from_provider_payloads,
    classify_macro_series_value,
    classify_signal_from_provider_payload,
    combine_channel_signal_states,
    signal_from_ecos_response,
    signal_from_fred_response,
    signal_from_kosis_response,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _signal(
    channel: str,
    state: int,
    *,
    series_id: str | None = None,
    confidence: float = 1.0,
    fallback_used: bool = False,
    warning_flags: tuple[str, ...] = (),
    as_of_timestamp: str = "2026-02-01T00:00:00",
    input_cutoff: str = "2026-03-20T00:00:00",
) -> MacroSeriesSignal:
    return MacroSeriesSignal(
        channel=channel,
        series_id=series_id or f"{channel}-signal",
        provider="fixture",
        state=state,
        as_of_timestamp=datetime.fromisoformat(as_of_timestamp),
        input_cutoff=datetime.fromisoformat(input_cutoff),
        transformation_method="fixture",
        retrieval_timestamp=datetime.fromisoformat("2026-03-22T00:00:00"),
        confidence=confidence,
        warning_flags=warning_flags,
        fallback_used=fallback_used,
    )


def test_macro_request_contract_builders_match_fixtures() -> None:
    assert build_ecos_request_contract(
        table_code="901Y009",
        item_codes=["0"],
        frequency="M",
    ) == _load_json(FIXTURE_ROOT / "ecos" / "statistic_search_request.json")
    assert build_kosis_request_contract(
        table_id="DT_1J22005",
        item_id="T1",
        frequency="M",
    ) == _load_json(FIXTURE_ROOT / "kosis" / "statistical_data_request.json")
    assert build_fred_request_contract(
        series_id="INDPRO",
        official_source="Federal Reserve",
    ) == _load_json(FIXTURE_ROOT / "us_macro" / "fred_series_request.json")


def test_macro_signal_builders_preserve_provider_metadata() -> None:
    ecos_signal = signal_from_ecos_response(
        channel="G",
        state=1,
        payload=_load_json(FIXTURE_ROOT / "ecos" / "statistic_search_response.json"),
    )
    kosis_signal = signal_from_kosis_response(
        channel="ED",
        state=1,
        payload=_load_json(FIXTURE_ROOT / "kosis" / "statistical_data_response.json"),
    )
    fred_signal = signal_from_fred_response(
        channel="G",
        state=1,
        payload=_load_json(FIXTURE_ROOT / "us_macro" / "fred_series_response.json"),
    )

    assert ecos_signal.series_id == "901Y009:0"
    assert ecos_signal.provider == "ecos"
    assert ecos_signal.as_of_timestamp == datetime.fromisoformat("2026-02-01T00:00:00")
    assert ecos_signal.input_cutoff == datetime.fromisoformat("2026-03-15T00:00:00")

    assert kosis_signal.series_id == "DT_1J22005:T1"
    assert kosis_signal.provider == "kosis"
    assert kosis_signal.input_cutoff == datetime.fromisoformat("2026-03-18T00:00:00")

    assert fred_signal.series_id == "INDPRO"
    assert fred_signal.provider == "fred"
    assert fred_signal.official_source == "Federal Reserve"
    assert fred_signal.input_cutoff == datetime.fromisoformat("2026-03-14T00:00:00")


def test_combine_channel_signal_states_uses_simple_mean() -> None:
    positive_state, positive_score = combine_channel_signal_states(
        [_signal("IC", 1), _signal("IC", 0)],
        neutral_band=0.25,
    )
    neutral_state, neutral_score = combine_channel_signal_states(
        [_signal("FC", 1), _signal("FC", -1)],
        neutral_band=0.25,
    )

    assert positive_score == 0.5
    assert positive_state == 1
    assert neutral_score == 0.0
    assert neutral_state == 0


def test_live_macro_data_source_builds_channel_states_and_fallback_metadata() -> None:
    data_source = LiveMacroDataSource(
        channel_signals={
            "G": [_signal("G", 1), _signal("G", 1, confidence=0.9)],
            "IC": [_signal("IC", 1), _signal("IC", 0, confidence=0.8)],
            "FC": [_signal("FC", -1), _signal("FC", 1)],
            "ED": [
                _signal("ED", 1),
                _signal(
                    "ED",
                    0,
                    confidence=0.6,
                    fallback_used=True,
                    warning_flags=("us_real_imports_goods_fallback_to_pce_goods",),
                    input_cutoff="2026-03-21T00:00:00",
                ),
            ],
            "FX": [_signal("FX", -1), _signal("FX", -1, confidence=0.95)],
        },
        source_name="ecos_kosis_fred_live",
        source_version="phase0-freeze-8230c76",
    )

    result = data_source.fetch_channel_states()

    assert result.source_name == "ecos_kosis_fred_live"
    assert result.source_version == "phase0-freeze-8230c76"
    assert result.channel_states == {"G": 1, "IC": 1, "FC": 0, "ED": 1, "FX": -1}
    assert result.confidence_by_channel["ED"] == 0.6
    assert result.fallback_mode == "degraded_live"
    assert result.warning_flags_by_channel["ED"] == [
        "us_real_imports_goods_fallback_to_pce_goods",
        "live_macro_fallback_signal_used",
    ]
    assert "us_real_imports_goods_fallback_to_pce_goods" in result.warnings
    assert result.input_cutoff == datetime.fromisoformat("2026-03-21T00:00:00")


def test_fixed_channel_roster_encodes_ed_fallback_only() -> None:
    assert FIXED_CHANNEL_SERIES_ROSTER["ED"].korea_series_id == "kr_exports_us_yoy_3mma"
    assert FIXED_CHANNEL_SERIES_ROSTER["ED"].us_series_id == "us_real_imports_goods_yoy_3mma"
    assert (
        FIXED_CHANNEL_SERIES_ROSTER["ED"].us_degraded_fallback_series_id
        == "us_real_pce_goods_yoy_3mma"
    )
    assert FIXED_CHANNEL_SERIES_ROSTER["G"].us_degraded_fallback_series_id is None
    assert FIXED_SERIES_CLASSIFIER_SPECS["us_real_pce_goods_yoy_3mma"].degraded_fallback_only


def test_classify_macro_series_value_applies_fixed_prd_thresholds() -> None:
    assert classify_macro_series_value("kr_ipi_yoy_3mma", 1.01) == 1
    assert classify_macro_series_value("kr_ipi_yoy_3mma", -1.01) == -1
    assert classify_macro_series_value("kr_ipi_yoy_3mma", 1.0) == 0

    assert classify_macro_series_value("kr_cpi_yoy_3mma", 2.8) == 1
    assert classify_macro_series_value("kr_cpi_yoy_3mma", 1.0) == -1
    assert classify_macro_series_value("kr_cpi_yoy_3mma", 2.0) == 0

    assert classify_macro_series_value("kr_credit_spread_z36", -0.6) == 1
    assert classify_macro_series_value("kr_credit_spread_z36", 0.6) == -1
    assert classify_macro_series_value("kr_credit_spread_z36", 0.1) == 0

    assert classify_macro_series_value("usdkrw_3m_log_return", 2.6) == 1
    assert classify_macro_series_value("broad_usd_3m_log_return", -2.1) == -1


def test_classify_macro_series_value_rejects_unknown_series() -> None:
    try:
        classify_macro_series_value("unknown_series", 0.0)
    except KeyError as exc:
        assert "unknown macro series classifier spec" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected classify_macro_series_value to reject unknown series")


def test_classify_signal_from_provider_payload_uses_fixed_thresholds() -> None:
    ecos_payload = {
        "provider": "ecos",
        "service": "StatisticSearch",
        "series": [
            {
                "table_code": "901Y009",
                "item_code": "0",
                "frequency": "M",
                "observation_date": "2026-02",
                "release_date": "2026-03-15",
                "retrieval_timestamp": "2026-03-22T00:02:00Z",
                "transformation_method": "yoy",
                "value": "2.8",
            }
        ],
    }
    fred_payload = {
        "provider": "us_macro",
        "adapter": "fred",
        "official_source": "Federal Reserve",
        "series": [
            {
                "series_id": "PCE_GOODS",
                "observation_date": "2026-02-01",
                "release_date": "2026-03-14",
                "retrieval_timestamp": "2026-03-22T00:04:00Z",
                "transformation_method": "yoy",
                "value": "-2.0",
            }
        ],
    }

    korea_signal = classify_signal_from_provider_payload("kr_cpi_yoy_3mma", ecos_payload)
    us_signal = classify_signal_from_provider_payload(
        "us_real_pce_goods_yoy_3mma",
        fred_payload,
    )

    assert korea_signal.channel == "IC"
    assert korea_signal.state == 1
    assert us_signal.channel == "ED"
    assert us_signal.state == -1
    assert us_signal.official_source == "Federal Reserve"


def test_build_fixed_channel_signal_map_uses_primary_series_when_present() -> None:
    series_signals = {
        "kr_ipi_yoy_3mma": _signal("G", 1, series_id="kr_ipi_yoy_3mma"),
        "us_ipi_yoy_3mma": _signal("G", 0, series_id="us_ipi_yoy_3mma"),
        "kr_cpi_yoy_3mma": _signal("IC", 1, series_id="kr_cpi_yoy_3mma"),
        "us_cpi_yoy_3mma": _signal("IC", 0, series_id="us_cpi_yoy_3mma"),
        "kr_credit_spread_z36": _signal("FC", -1, series_id="kr_credit_spread_z36"),
        "us_credit_spread_z36": _signal("FC", 1, series_id="us_credit_spread_z36"),
        "kr_exports_us_yoy_3mma": _signal("ED", 1, series_id="kr_exports_us_yoy_3mma"),
        "us_real_imports_goods_yoy_3mma": _signal(
            "ED",
            1,
            series_id="us_real_imports_goods_yoy_3mma",
        ),
        "usdkrw_3m_log_return": _signal("FX", -1, series_id="usdkrw_3m_log_return"),
        "broad_usd_3m_log_return": _signal("FX", -1, series_id="broad_usd_3m_log_return"),
    }

    signal_map = build_fixed_channel_signal_map(series_signals)

    assert signal_map["ED"][1].series_id == "us_real_imports_goods_yoy_3mma"
    assert signal_map["ED"][1].fallback_used is False


def test_build_fixed_channel_signal_map_uses_ed_fallback_only_in_degraded_mode() -> None:
    series_signals = {
        "kr_ipi_yoy_3mma": _signal("G", 1, series_id="kr_ipi_yoy_3mma"),
        "us_ipi_yoy_3mma": _signal("G", 0, series_id="us_ipi_yoy_3mma"),
        "kr_cpi_yoy_3mma": _signal("IC", 1, series_id="kr_cpi_yoy_3mma"),
        "us_cpi_yoy_3mma": _signal("IC", 0, series_id="us_cpi_yoy_3mma"),
        "kr_credit_spread_z36": _signal("FC", -1, series_id="kr_credit_spread_z36"),
        "us_credit_spread_z36": _signal("FC", 1, series_id="us_credit_spread_z36"),
        "kr_exports_us_yoy_3mma": _signal("ED", 1, series_id="kr_exports_us_yoy_3mma"),
        "us_real_pce_goods_yoy_3mma": _signal(
            "ED",
            0,
            series_id="us_real_pce_goods_yoy_3mma",
        ),
        "usdkrw_3m_log_return": _signal("FX", -1, series_id="usdkrw_3m_log_return"),
        "broad_usd_3m_log_return": _signal("FX", -1, series_id="broad_usd_3m_log_return"),
    }

    signal_map = build_fixed_channel_signal_map(series_signals, degraded_mode=True)

    assert signal_map["ED"][1].series_id == "us_real_pce_goods_yoy_3mma"
    assert signal_map["ED"][1].fallback_used is True
    assert signal_map["ED"][1].warning_flags == (
        "us_real_imports_goods_yoy_3mma_fallback_signal_used",
    )


def test_live_macro_data_source_from_fixed_series_signals_builds_channel_map() -> None:
    series_signals = {
        "kr_ipi_yoy_3mma": _signal("G", 1, series_id="kr_ipi_yoy_3mma"),
        "us_ipi_yoy_3mma": _signal("G", 1, series_id="us_ipi_yoy_3mma"),
        "kr_cpi_yoy_3mma": _signal("IC", 1, series_id="kr_cpi_yoy_3mma"),
        "us_cpi_yoy_3mma": _signal("IC", 0, series_id="us_cpi_yoy_3mma"),
        "kr_credit_spread_z36": _signal("FC", -1, series_id="kr_credit_spread_z36"),
        "us_credit_spread_z36": _signal("FC", 1, series_id="us_credit_spread_z36"),
        "kr_exports_us_yoy_3mma": _signal("ED", 1, series_id="kr_exports_us_yoy_3mma"),
        "us_real_pce_goods_yoy_3mma": _signal(
            "ED",
            0,
            series_id="us_real_pce_goods_yoy_3mma",
        ),
        "usdkrw_3m_log_return": _signal("FX", -1, series_id="usdkrw_3m_log_return"),
        "broad_usd_3m_log_return": _signal("FX", -1, series_id="broad_usd_3m_log_return"),
    }

    result = LiveMacroDataSource.from_fixed_series_signals(
        series_signals=series_signals,
        degraded_mode=True,
        source_name="fixed-roster-live",
    ).fetch_channel_states()

    assert result.source_name == "fixed-roster-live"
    assert result.channel_states["G"] == 1
    assert result.channel_states["ED"] == 1
    assert result.fallback_mode == "degraded_live"
    assert "us_real_imports_goods_yoy_3mma_fallback_signal_used" in result.warnings


def test_build_live_macro_data_source_from_provider_payloads_supports_degraded_ed_fallback(
) -> None:
    series_payloads = {
        "kr_ipi_yoy_3mma": {
            "provider": "ecos",
            "service": "StatisticSearch",
            "series": [
                {
                    "table_code": "901Y009",
                    "item_code": "0",
                    "observation_date": "2026-02",
                    "release_date": "2026-03-15",
                    "retrieval_timestamp": "2026-03-22T00:02:00Z",
                    "transformation_method": "yoy",
                    "value": "1.2",
                }
            ],
        },
        "us_ipi_yoy_3mma": {
            "provider": "us_macro",
            "adapter": "fred",
            "official_source": "Federal Reserve",
            "series": [
                {
                    "series_id": "INDPRO",
                    "observation_date": "2026-02-01",
                    "release_date": "2026-03-14",
                    "retrieval_timestamp": "2026-03-22T00:04:00Z",
                    "transformation_method": "yoy",
                    "value": "1.3",
                }
            ],
        },
        "kr_cpi_yoy_3mma": {
            "provider": "ecos",
            "service": "StatisticSearch",
            "series": [
                {
                    "table_code": "901Y009",
                    "item_code": "0",
                    "observation_date": "2026-02",
                    "release_date": "2026-03-15",
                    "retrieval_timestamp": "2026-03-22T00:02:00Z",
                    "transformation_method": "yoy",
                    "value": "2.9",
                }
            ],
        },
        "us_cpi_yoy_3mma": {
            "provider": "us_macro",
            "adapter": "fred",
            "official_source": "BLS",
            "series": [
                {
                    "series_id": "CPIAUCSL",
                    "observation_date": "2026-02-01",
                    "release_date": "2026-03-14",
                    "retrieval_timestamp": "2026-03-22T00:04:00Z",
                    "transformation_method": "yoy",
                    "value": "2.0",
                }
            ],
        },
        "kr_credit_spread_z36": {
            "provider": "ecos",
            "service": "StatisticSearch",
            "series": [
                {
                    "table_code": "901Y009",
                    "item_code": "0",
                    "observation_date": "2026-02",
                    "release_date": "2026-03-15",
                    "retrieval_timestamp": "2026-03-22T00:02:00Z",
                    "transformation_method": "zscore",
                    "value": "-0.6",
                }
            ],
        },
        "us_credit_spread_z36": {
            "provider": "us_macro",
            "adapter": "fred",
            "official_source": "Federal Reserve",
            "series": [
                {
                    "series_id": "BAA10Y",
                    "observation_date": "2026-02-01",
                    "release_date": "2026-03-14",
                    "retrieval_timestamp": "2026-03-22T00:04:00Z",
                    "transformation_method": "zscore",
                    "value": "0.1",
                }
            ],
        },
        "kr_exports_us_yoy_3mma": {
            "provider": "kosis",
            "service": "statistical_data",
            "series": [
                {
                    "table_id": "DT_1J22005",
                    "item_id": "T1",
                    "observation_date": "2026-02",
                    "release_date": "2026-03-18",
                    "retrieval_timestamp": "2026-03-22T00:03:00Z",
                    "transformation_method": "yoy",
                    "value": "4.0",
                }
            ],
        },
        "us_real_pce_goods_yoy_3mma": {
            "provider": "us_macro",
            "adapter": "fred",
            "official_source": "BEA",
            "series": [
                {
                    "series_id": "PCE_GOODS",
                    "observation_date": "2026-02-01",
                    "release_date": "2026-03-14",
                    "retrieval_timestamp": "2026-03-22T00:04:00Z",
                    "transformation_method": "yoy",
                    "value": "1.8",
                }
            ],
        },
        "usdkrw_3m_log_return": {
            "provider": "ecos",
            "service": "StatisticSearch",
            "series": [
                {
                    "table_code": "901Y009",
                    "item_code": "0",
                    "observation_date": "2026-02",
                    "release_date": "2026-03-15",
                    "retrieval_timestamp": "2026-03-22T00:02:00Z",
                    "transformation_method": "log_return",
                    "value": "2.6",
                }
            ],
        },
        "broad_usd_3m_log_return": {
            "provider": "us_macro",
            "adapter": "fred",
            "official_source": "Federal Reserve",
            "series": [
                {
                    "series_id": "TWEXB",
                    "observation_date": "2026-02-01",
                    "release_date": "2026-03-14",
                    "retrieval_timestamp": "2026-03-22T00:04:00Z",
                    "transformation_method": "log_return",
                    "value": "2.1",
                }
            ],
        },
    }

    result = build_live_macro_data_source_from_provider_payloads(
        series_payloads,
        degraded_mode=True,
        source_name="provider-payload-live",
        source_version="phase0-freeze-8230c76",
    ).fetch_channel_states()

    assert result.source_name == "provider-payload-live"
    assert result.source_version == "phase0-freeze-8230c76"
    assert result.channel_states == {"G": 1, "IC": 1, "FC": 1, "ED": 1, "FX": 1}
    assert result.fallback_mode == "degraded_live"
    assert "us_real_imports_goods_yoy_3mma_fallback_signal_used" in result.warnings
