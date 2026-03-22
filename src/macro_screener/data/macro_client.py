from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol, Sequence

import httpx

from macro_screener.data.reference import DEFAULT_NEUTRAL_BANDS
from macro_screener.db import SnapshotRegistry
from macro_screener.models import ChannelState
from macro_screener.serialization import parse_datetime

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
DEFAULT_CHANNEL_STATES: dict[str, int] = {"G": 1, "IC": -1, "FC": 0, "ED": 1, "FX": 1}


@dataclass(frozen=True, slots=True)
class MacroLoadResult:
    channel_states: dict[str, int]
    source_name: str
    warnings: list[str] = field(default_factory=list)
    as_of_timestamp: datetime | None = None
    input_cutoff: datetime | None = None
    source_version: str | None = None
    fallback_mode: str | None = None
    confidence_by_channel: dict[str, float] = field(default_factory=dict)
    warning_flags_by_channel: dict[str, list[str]] = field(default_factory=dict)

    @property
    def source(self) -> str:
        return self.source_name


class MacroDataSource(Protocol):
    def fetch_channel_states(self) -> MacroLoadResult: ...


@dataclass(frozen=True, slots=True)
class MacroSeriesSignal:
    channel: str
    series_id: str
    provider: str
    state: int
    as_of_timestamp: datetime
    input_cutoff: datetime
    transformation_method: str
    retrieval_timestamp: datetime | None = None
    official_source: str | None = None
    confidence: float = 1.0
    warning_flags: tuple[str, ...] = ()
    fallback_used: bool = False

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f"unsupported macro signal channel: {self.channel}")
        if self.state not in {-1, 0, 1}:
            raise ValueError(f"macro signal state must be -1, 0, or 1, got {self.state}")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("macro signal confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class MacroSeriesClassifierSpec:
    series_id: str
    channel: str
    positive_cutoff: float
    negative_cutoff: float
    positive_when: str = "higher"
    degraded_fallback_only: bool = False

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f"unsupported classifier channel: {self.channel}")
        if self.positive_when not in {"higher", "lower"}:
            raise ValueError("positive_when must be 'higher' or 'lower'")


@dataclass(frozen=True, slots=True)
class MacroChannelRoster:
    korea_series_id: str
    us_series_id: str
    us_degraded_fallback_series_id: str | None = None


FIXED_CHANNEL_SERIES_ROSTER: dict[str, MacroChannelRoster] = {
    "G": MacroChannelRoster(
        korea_series_id="kr_ipi_yoy_3mma",
        us_series_id="us_ipi_yoy_3mma",
    ),
    "IC": MacroChannelRoster(
        korea_series_id="kr_cpi_yoy_3mma",
        us_series_id="us_cpi_yoy_3mma",
    ),
    "FC": MacroChannelRoster(
        korea_series_id="kr_credit_spread_z36",
        us_series_id="us_credit_spread_z36",
    ),
    "ED": MacroChannelRoster(
        korea_series_id="kr_exports_us_yoy_3mma",
        us_series_id="us_real_imports_goods_yoy_3mma",
        us_degraded_fallback_series_id="us_real_pce_goods_yoy_3mma",
    ),
    "FX": MacroChannelRoster(
        korea_series_id="usdkrw_3m_log_return",
        us_series_id="broad_usd_3m_log_return",
    ),
}

FIXED_SERIES_CLASSIFIER_SPECS: dict[str, MacroSeriesClassifierSpec] = {
    "kr_ipi_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="kr_ipi_yoy_3mma",
        channel="G",
        positive_cutoff=1.0,
        negative_cutoff=-1.0,
    ),
    "us_ipi_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="us_ipi_yoy_3mma",
        channel="G",
        positive_cutoff=1.0,
        negative_cutoff=-1.0,
    ),
    "kr_cpi_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="kr_cpi_yoy_3mma",
        channel="IC",
        positive_cutoff=2.75,
        negative_cutoff=1.25,
    ),
    "us_cpi_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="us_cpi_yoy_3mma",
        channel="IC",
        positive_cutoff=2.75,
        negative_cutoff=1.25,
    ),
    "kr_credit_spread_z36": MacroSeriesClassifierSpec(
        series_id="kr_credit_spread_z36",
        channel="FC",
        positive_cutoff=-0.5,
        negative_cutoff=0.5,
        positive_when="lower",
    ),
    "us_credit_spread_z36": MacroSeriesClassifierSpec(
        series_id="us_credit_spread_z36",
        channel="FC",
        positive_cutoff=-0.5,
        negative_cutoff=0.5,
        positive_when="lower",
    ),
    "kr_exports_us_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="kr_exports_us_yoy_3mma",
        channel="ED",
        positive_cutoff=2.0,
        negative_cutoff=-2.0,
    ),
    "us_real_imports_goods_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="us_real_imports_goods_yoy_3mma",
        channel="ED",
        positive_cutoff=1.5,
        negative_cutoff=-1.5,
    ),
    "us_real_pce_goods_yoy_3mma": MacroSeriesClassifierSpec(
        series_id="us_real_pce_goods_yoy_3mma",
        channel="ED",
        positive_cutoff=1.5,
        negative_cutoff=-1.5,
        degraded_fallback_only=True,
    ),
    "usdkrw_3m_log_return": MacroSeriesClassifierSpec(
        series_id="usdkrw_3m_log_return",
        channel="FX",
        positive_cutoff=2.5,
        negative_cutoff=-2.5,
    ),
    "broad_usd_3m_log_return": MacroSeriesClassifierSpec(
        series_id="broad_usd_3m_log_return",
        channel="FX",
        positive_cutoff=2.0,
        negative_cutoff=-2.0,
    ),
}


@dataclass(frozen=True, slots=True)
class LiveMacroDataSource:
    channel_signals: Mapping[str, Sequence[MacroSeriesSignal]]
    source_name: str = "live_macro"
    source_version: str | None = None

    @classmethod
    def from_fixed_series_signals(
        cls,
        *,
        series_signals: Mapping[str, MacroSeriesSignal],
        degraded_mode: bool = False,
        source_name: str = "live_macro",
        source_version: str | None = None,
    ) -> "LiveMacroDataSource":
        return cls(
            channel_signals=build_fixed_channel_signal_map(
                series_signals,
                degraded_mode=degraded_mode,
            ),
            source_name=source_name,
            source_version=source_version,
        )

    def fetch_channel_states(self) -> MacroLoadResult:
        channel_states: dict[str, int] = {}
        confidence_by_channel: dict[str, float] = {}
        warning_flags_by_channel: dict[str, list[str]] = {}
        warnings: list[str] = []
        as_of_values: list[datetime] = []
        cutoff_values: list[datetime] = []
        fallback_used = False

        for channel in CHANNELS:
            signals = list(self.channel_signals.get(channel, ()))
            if not signals:
                raise ValueError(f"missing live macro signals for channel: {channel}")
            combined_state, _combined_score = combine_channel_signal_states(
                signals,
                neutral_band=float(DEFAULT_NEUTRAL_BANDS[channel]),
            )
            channel_states[channel] = combined_state
            confidence_by_channel[channel] = min(signal.confidence for signal in signals)
            channel_flags = _dedupe_flags(
                flag
                for signal in signals
                for flag in (
                    *signal.warning_flags,
                    *(("live_macro_fallback_signal_used",) if signal.fallback_used else ()),
                )
            )
            if channel_flags:
                warning_flags_by_channel[channel] = channel_flags
                warnings.extend(channel_flags)
            if any(signal.fallback_used for signal in signals):
                fallback_used = True
            as_of_values.extend(signal.as_of_timestamp for signal in signals)
            cutoff_values.extend(signal.input_cutoff for signal in signals)

        return MacroLoadResult(
            channel_states=channel_states,
            source_name=self.source_name,
            warnings=_dedupe_flags(warnings),
            as_of_timestamp=max(as_of_values) if as_of_values else None,
            input_cutoff=max(cutoff_values) if cutoff_values else None,
            source_version=self.source_version,
            fallback_mode="degraded_live" if fallback_used else None,
            confidence_by_channel=confidence_by_channel,
            warning_flags_by_channel=warning_flags_by_channel,
        )


@dataclass(frozen=True, slots=True)
class ManualMacroDataSource:
    channel_states: dict[str, int]
    source_name: str = "manual"

    def fetch_channel_states(self) -> MacroLoadResult:
        missing = [channel for channel in CHANNELS if channel not in self.channel_states]
        if missing:
            raise ValueError(f"missing channel states: {', '.join(missing)}")
        invalid = {value for value in self.channel_states.values() if value not in {-1, 0, 1}}
        if invalid:
            raise ValueError(f"invalid channel states: {sorted(invalid)}")
        return MacroLoadResult(
            channel_states=dict(self.channel_states),
            source_name=self.source_name,
        )


@dataclass(frozen=True, slots=True)
class PersistedMacroDataSource:
    store: SnapshotRegistry

    def fetch_channel_states(self) -> MacroLoadResult:
        snapshot = self.store.load_last_channel_state_snapshot()
        if snapshot is None:
            raise ValueError("no persisted macro channel states available")
        states = snapshot["channel_states"]
        metadata = snapshot.get("metadata", {})
        warning_flags = list(metadata.get("warning_flags", []))
        source_name = str(metadata.get("source_name", "last_known"))
        source_version = (
            str(metadata["source_version"])
            if metadata.get("source_version") is not None
            else None
        )
        fallback_mode = (
            str(metadata["fallback_mode"])
            if metadata.get("fallback_mode") is not None
            else "last_known_channel_states"
        )
        warning_flags_by_channel = {
            channel: list(warning_flags) for channel in {state.channel for state in states}
        }
        confidence_by_channel = {
            str(channel): float(value)
            for channel, value in metadata.get("confidence_by_channel", {}).items()
        }
        as_of_timestamp_raw = metadata.get("as_of_timestamp")
        input_cutoff_raw = metadata.get("input_cutoff")
        as_of_timestamp = (
            None
            if as_of_timestamp_raw is None
            else datetime.fromisoformat(str(as_of_timestamp_raw))
        )
        input_cutoff = (
            None if input_cutoff_raw is None else datetime.fromisoformat(str(input_cutoff_raw))
        )
        return MacroLoadResult(
            channel_states={state.channel: state.state for state in states},
            source_name=source_name,
            warnings=warning_flags,
            as_of_timestamp=as_of_timestamp,
            input_cutoff=input_cutoff,
            source_version=source_version,
            fallback_mode=fallback_mode,
            confidence_by_channel=confidence_by_channel,
            warning_flags_by_channel=warning_flags_by_channel,
        )


def last_known_channel_states(store: SnapshotRegistry) -> list[ChannelState] | None:
    return store.load_last_channel_states()


def build_ecos_request_contract(
    *,
    table_code: str,
    item_codes: Sequence[str],
    frequency: str,
) -> dict[str, Any]:
    return {
        "provider": "ecos",
        "service": "StatisticSearch",
        "table_code": table_code,
        "item_codes": [str(item) for item in item_codes],
        "frequency": frequency,
    }


def build_kosis_request_contract(
    *,
    table_id: str,
    item_id: str,
    frequency: str,
) -> dict[str, Any]:
    return {
        "provider": "kosis",
        "service": "statistical_data",
        "table_id": table_id,
        "item_id": item_id,
        "frequency": frequency,
    }


def build_fred_request_contract(
    *,
    series_id: str,
    official_source: str,
    vintage_mode: str = "current",
    adapter: str = "fred",
) -> dict[str, Any]:
    return {
        "provider": "us_macro",
        "adapter": adapter,
        "series_id": series_id,
        "official_source": official_source,
        "vintage_mode": vintage_mode,
    }


def signal_from_ecos_response(
    *,
    channel: str,
    state: int,
    payload: Mapping[str, Any],
    series_index: int = 0,
    confidence: float = 1.0,
    warning_flags: Sequence[str] = (),
    fallback_used: bool = False,
) -> MacroSeriesSignal:
    series = _extract_series_record(payload, series_index=series_index, expected_provider="ecos")
    item_code = str(series.get("item_code") or "").strip()
    series_id = (
        str(series["table_code"]) if not item_code else f"{series['table_code']}:{item_code}"
    )
    return _build_signal_from_series_record(
        channel=channel,
        state=state,
        provider="ecos",
        series_id=series_id,
        transformation_method=str(series.get("transformation_method") or "unknown"),
        observation_date=str(series.get("observation_date") or ""),
        release_date=str(series.get("release_date") or ""),
        retrieval_timestamp=str(series.get("retrieval_timestamp") or ""),
        official_source=None,
        confidence=confidence,
        warning_flags=warning_flags,
        fallback_used=fallback_used,
    )


def signal_from_kosis_response(
    *,
    channel: str,
    state: int,
    payload: Mapping[str, Any],
    series_index: int = 0,
    confidence: float = 1.0,
    warning_flags: Sequence[str] = (),
    fallback_used: bool = False,
) -> MacroSeriesSignal:
    series = _extract_series_record(payload, series_index=series_index, expected_provider="kosis")
    series_id = f"{series['table_id']}:{series['item_id']}"
    return _build_signal_from_series_record(
        channel=channel,
        state=state,
        provider="kosis",
        series_id=series_id,
        transformation_method=str(series.get("transformation_method") or "unknown"),
        observation_date=str(series.get("observation_date") or ""),
        release_date=str(series.get("release_date") or ""),
        retrieval_timestamp=str(series.get("retrieval_timestamp") or ""),
        official_source=None,
        confidence=confidence,
        warning_flags=warning_flags,
        fallback_used=fallback_used,
    )


def signal_from_fred_response(
    *,
    channel: str,
    state: int,
    payload: Mapping[str, Any],
    series_index: int = 0,
    confidence: float = 1.0,
    warning_flags: Sequence[str] = (),
    fallback_used: bool = False,
) -> MacroSeriesSignal:
    series = _extract_series_record(
        payload,
        series_index=series_index,
        expected_provider="us_macro",
    )
    return _build_signal_from_series_record(
        channel=channel,
        state=state,
        provider=str(payload.get("adapter") or "fred"),
        series_id=str(series.get("series_id") or ""),
        transformation_method=str(series.get("transformation_method") or "unknown"),
        observation_date=str(series.get("observation_date") or ""),
        release_date=str(series.get("release_date") or ""),
        retrieval_timestamp=str(series.get("retrieval_timestamp") or ""),
        official_source=(
            str(payload["official_source"]) if payload.get("official_source") is not None else None
        ),
        confidence=confidence,
        warning_flags=warning_flags,
        fallback_used=fallback_used,
    )


def combine_channel_signal_states(
    signals: Sequence[MacroSeriesSignal],
    *,
    neutral_band: float,
) -> tuple[int, float]:
    if not signals:
        raise ValueError("cannot combine an empty macro signal set")
    combined_score = sum(signal.state for signal in signals) / len(signals)
    if combined_score > neutral_band:
        return 1, combined_score
    if combined_score < -neutral_band:
        return -1, combined_score
    return 0, combined_score


def _extract_series_record(
    payload: Mapping[str, Any],
    *,
    series_index: int,
    expected_provider: str,
) -> Mapping[str, Any]:
    provider = str(payload.get("provider") or "").strip()
    if provider != expected_provider:
        raise ValueError(f"expected {expected_provider} payload, got {provider}")
    raw_series = payload.get("series", [])
    if not isinstance(raw_series, Sequence) or isinstance(raw_series, (str, bytes, bytearray)):
        raise ValueError("macro provider payload must include a series list")
    try:
        record = raw_series[series_index]
    except IndexError as exc:
        raise ValueError(f"macro provider payload missing series index {series_index}") from exc
    if not isinstance(record, Mapping):
        raise ValueError("macro provider series entries must be mappings")
    return record


def _build_signal_from_series_record(
    *,
    channel: str,
    state: int,
    provider: str,
    series_id: str,
    transformation_method: str,
    observation_date: str,
    release_date: str,
    retrieval_timestamp: str,
    official_source: str | None,
    confidence: float,
    warning_flags: Sequence[str],
    fallback_used: bool,
) -> MacroSeriesSignal:
    as_of_timestamp = _parse_series_timestamp(observation_date)
    input_cutoff = _parse_series_timestamp(release_date)
    retrieval = _parse_series_timestamp(retrieval_timestamp)
    return MacroSeriesSignal(
        channel=channel,
        series_id=series_id,
        provider=provider,
        state=state,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        transformation_method=transformation_method,
        retrieval_timestamp=retrieval,
        official_source=official_source,
        confidence=confidence,
        warning_flags=tuple(_dedupe_flags(warning_flags)),
        fallback_used=fallback_used,
    )


def classify_macro_series_value(series_id: str, value: float) -> int:
    spec = FIXED_SERIES_CLASSIFIER_SPECS.get(series_id)
    if spec is None:
        raise KeyError(f"unknown macro series classifier spec: {series_id}")
    if spec.positive_when == "lower":
        if value < spec.positive_cutoff:
            return 1
        if value > spec.negative_cutoff:
            return -1
        return 0
    if value > spec.positive_cutoff:
        return 1
    if value < spec.negative_cutoff:
        return -1
    return 0


def classify_signal_from_provider_payload(
    series_id: str,
    payload: Mapping[str, Any],
    *,
    series_index: int = 0,
    confidence: float = 1.0,
    warning_flags: Sequence[str] = (),
    fallback_used: bool = False,
) -> MacroSeriesSignal:
    spec = FIXED_SERIES_CLASSIFIER_SPECS.get(series_id)
    if spec is None:
        raise KeyError(f"unknown macro series classifier spec: {series_id}")
    state = classify_macro_series_value(
        series_id,
        _extract_series_numeric_value(payload, series_index=series_index),
    )
    provider = str(payload.get("provider") or "").strip()
    if provider == "ecos":
        return signal_from_ecos_response(
            channel=spec.channel,
            state=state,
            payload=payload,
            series_index=series_index,
            confidence=confidence,
            warning_flags=warning_flags,
            fallback_used=fallback_used,
        )
    if provider == "kosis":
        return signal_from_kosis_response(
            channel=spec.channel,
            state=state,
            payload=payload,
            series_index=series_index,
            confidence=confidence,
            warning_flags=warning_flags,
            fallback_used=fallback_used,
        )
    if provider == "us_macro":
        return signal_from_fred_response(
            channel=spec.channel,
            state=state,
            payload=payload,
            series_index=series_index,
            confidence=confidence,
            warning_flags=warning_flags,
            fallback_used=fallback_used,
        )
    raise ValueError(f"unsupported macro provider payload: {provider}")


def build_live_macro_data_source_from_provider_payloads(
    series_payloads: Mapping[str, Mapping[str, Any]],
    *,
    degraded_mode: bool = False,
    source_name: str = "live_macro",
    source_version: str | None = None,
    confidence_by_series: Mapping[str, float] | None = None,
    warning_flags_by_series: Mapping[str, Sequence[str]] | None = None,
) -> LiveMacroDataSource:
    series_signals: dict[str, MacroSeriesSignal] = {}
    confidence_map = confidence_by_series or {}
    warning_map = warning_flags_by_series or {}
    for series_id, payload in series_payloads.items():
        series_signals[series_id] = classify_signal_from_provider_payload(
            series_id,
            payload,
            confidence=float(confidence_map.get(series_id, 1.0)),
            warning_flags=warning_map.get(series_id, ()),
        )
    return LiveMacroDataSource.from_fixed_series_signals(
        series_signals=series_signals,
        degraded_mode=degraded_mode,
        source_name=source_name,
        source_version=source_version,
    )


def build_fixed_channel_signal_map(
    series_signals: Mapping[str, MacroSeriesSignal],
    *,
    degraded_mode: bool = False,
) -> dict[str, tuple[MacroSeriesSignal, MacroSeriesSignal]]:
    channel_signals: dict[str, tuple[MacroSeriesSignal, MacroSeriesSignal]] = {}
    for channel, roster in FIXED_CHANNEL_SERIES_ROSTER.items():
        korea_signal = _require_series_signal(series_signals, roster.korea_series_id)
        us_signal = series_signals.get(roster.us_series_id)
        if us_signal is None:
            fallback_series_id = roster.us_degraded_fallback_series_id
            if not degraded_mode or fallback_series_id is None:
                raise ValueError(
                    f"missing required primary US series for {channel}: {roster.us_series_id}"
                )
            fallback_signal = _require_series_signal(series_signals, fallback_series_id)
            us_signal = _mark_degraded_fallback_signal(
                fallback_signal,
                primary_series_id=roster.us_series_id,
            )
        channel_signals[channel] = (korea_signal, us_signal)
    return channel_signals


def _parse_series_timestamp(value: str) -> datetime:
    text = value.strip()
    if len(text) == 7:
        text = f"{text}-01T00:00:00"
    elif len(text) == 10:
        text = f"{text}T00:00:00"
    return parse_datetime(text)


def _dedupe_flags(flags: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(flag) for flag in flags if str(flag).strip()))


def _extract_series_numeric_value(
    payload: Mapping[str, Any],
    *,
    series_index: int,
) -> float:
    provider = str(payload.get("provider") or "").strip()
    record = _extract_series_record(
        payload,
        series_index=series_index,
        expected_provider=provider,
    )
    raw_value = record.get("value")
    if raw_value is None:
        raise ValueError(f"macro provider payload missing numeric value for provider {provider}")
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"macro provider value is not numeric: {raw_value}") from exc


def _require_series_signal(
    series_signals: Mapping[str, MacroSeriesSignal],
    series_id: str,
) -> MacroSeriesSignal:
    signal = series_signals.get(series_id)
    if signal is None:
        raise ValueError(f"missing required macro series signal: {series_id}")
    return signal


def _mark_degraded_fallback_signal(
    signal: MacroSeriesSignal,
    *,
    primary_series_id: str,
) -> MacroSeriesSignal:
    return replace(
        signal,
        warning_flags=tuple(
            _dedupe_flags(
                [*signal.warning_flags, f"{primary_series_id}_fallback_signal_used"]
            )
        ),
        fallback_used=True,
    )


ECOS_API_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
FRED_OBSERVATIONS_API_URL = "https://api.stlouisfed.org/fred/series/observations"

ECOS_RUNTIME_SERIES_SPECS: dict[str, dict[str, Any]] = {
    "kr_ipi_yoy_3mma": {
        "table_code": "901Y033",
        "frequency": "M",
        "item_codes": ("A00", "2"),
        "official_source": "Bank of Korea ECOS",
        "transformation_method": "yoy_3mma",
    },
    "kr_cpi_yoy_3mma": {
        "table_code": "901Y009",
        "frequency": "M",
        "item_codes": ("0",),
        "official_source": "Bank of Korea ECOS",
        "transformation_method": "yoy_3mma",
    },
    "kr_exports_us_yoy_3mma": {
        "table_code": "901Y121",
        "frequency": "M",
        "item_codes": ("T002", "US"),
        "official_source": "Bank of Korea ECOS",
        "transformation_method": "yoy_3mma",
    },
    "usdkrw_3m_log_return": {
        "table_code": "731Y006",
        "frequency": "M",
        "item_codes": ("0000003",),
        "official_source": "Bank of Korea ECOS",
        "transformation_method": "log_return_3m",
    },
}

FRED_RUNTIME_SERIES_SPECS: dict[str, dict[str, Any]] = {
    "us_ipi_yoy_3mma": {
        "source_series_id": "INDPRO",
        "adapter": "fred",
        "official_source": "Federal Reserve",
        "transformation_method": "yoy_3mma",
    },
    "us_cpi_yoy_3mma": {
        "source_series_id": "CPIAUCSL",
        "adapter": "fred",
        "official_source": "BLS via FRED",
        "transformation_method": "yoy_3mma",
    },
    "us_credit_spread_z36": {
        "source_series_id": "BAA10YM",
        "adapter": "fred",
        "official_source": "Moody's/Federal Reserve via FRED",
        "transformation_method": "zscore36_3mma",
    },
    "us_real_imports_goods_yoy_3mma": {
        "source_series_id": "A255RO1Q156NBEA",
        "adapter": "fred",
        "official_source": "BEA via FRED",
        "transformation_method": "yoy_3obs_mean",
    },
    "us_real_pce_goods_yoy_3mma": {
        "source_series_id": "DGDSRX1",
        "adapter": "fred",
        "official_source": "BEA via FRED",
        "transformation_method": "yoy_3mma",
    },
    "broad_usd_3m_log_return": {
        "source_series_id": "TWEXBGSMTH",
        "adapter": "fred",
        "official_source": "Federal Reserve via FRED",
        "transformation_method": "log_return_3m",
    },
}


def load_live_macro_data_source(
    *,
    as_of_timestamp: str | datetime,
    input_cutoff: str | datetime,
    ecos_api_key_env: str = "ECOS_API_KEY",
    fred_api_key_env: str = "FRED_API_KEY",
    source_name: str = "ecos_fred_live",
    source_version: str | None = None,
) -> LiveMacroDataSource:
    as_of_dt = parse_datetime(as_of_timestamp)
    cutoff_dt = parse_datetime(input_cutoff)
    retrieval_timestamp = datetime.now(UTC).isoformat()
    ecos_api_key = _require_api_key(ecos_api_key_env)
    fred_api_key = _require_api_key(fred_api_key_env)

    series_payloads: dict[str, dict[str, Any]] = {}
    confidence_by_series: dict[str, float] = {}
    warning_flags_by_series: dict[str, Sequence[str]] = {}
    degraded_mode = False

    for logical_series_id in ("kr_ipi_yoy_3mma", "kr_cpi_yoy_3mma", "kr_exports_us_yoy_3mma"):
        spec = ECOS_RUNTIME_SERIES_SPECS[logical_series_id]
        value, observation_date = _compute_ecos_yoy_3mma(
            table_code=str(spec["table_code"]),
            item_codes=tuple(str(item) for item in spec["item_codes"]),
            as_of_timestamp=as_of_dt,
            api_key=ecos_api_key,
        )
        series_payloads[logical_series_id] = _build_ecos_runtime_payload(
            table_code=str(spec["table_code"]),
            item_codes=tuple(str(item) for item in spec["item_codes"]),
            observation_date=observation_date,
            release_date=cutoff_dt,
            retrieval_timestamp=retrieval_timestamp,
            transformation_method=str(spec["transformation_method"]),
            value=value,
        )

    kr_credit_value, kr_credit_as_of = _compute_ecos_credit_spread_z36(
        as_of_timestamp=as_of_dt,
        api_key=ecos_api_key,
    )
    series_payloads["kr_credit_spread_z36"] = _build_ecos_runtime_payload(
        table_code="721Y001",
        item_codes=("7020000", "5020000"),
        observation_date=kr_credit_as_of,
        release_date=cutoff_dt,
        retrieval_timestamp=retrieval_timestamp,
        transformation_method="zscore36_3mma",
        value=kr_credit_value,
    )

    kr_fx_value, kr_fx_as_of = _compute_ecos_log_return_3m(
        table_code=str(ECOS_RUNTIME_SERIES_SPECS["usdkrw_3m_log_return"]["table_code"]),
        item_codes=tuple(
            str(item) for item in ECOS_RUNTIME_SERIES_SPECS["usdkrw_3m_log_return"]["item_codes"]
        ),
        as_of_timestamp=as_of_dt,
        api_key=ecos_api_key,
    )
    series_payloads["usdkrw_3m_log_return"] = _build_ecos_runtime_payload(
        table_code="731Y006",
        item_codes=("0000003",),
        observation_date=kr_fx_as_of,
        release_date=cutoff_dt,
        retrieval_timestamp=retrieval_timestamp,
        transformation_method="log_return_3m",
        value=kr_fx_value,
    )

    for logical_series_id in ("us_ipi_yoy_3mma", "us_cpi_yoy_3mma"):
        spec = FRED_RUNTIME_SERIES_SPECS[logical_series_id]
        value, observation_date = _compute_fred_yoy_3mma(
            source_series_id=str(spec["source_series_id"]),
            as_of_timestamp=as_of_dt,
            api_key=fred_api_key,
        )
        series_payloads[logical_series_id] = _build_fred_runtime_payload(
            source_series_id=str(spec["source_series_id"]),
            adapter=str(spec["adapter"]),
            official_source=str(spec["official_source"]),
            observation_date=observation_date,
            release_date=cutoff_dt,
            retrieval_timestamp=retrieval_timestamp,
            transformation_method=str(spec["transformation_method"]),
            value=value,
        )

    us_credit_value, us_credit_as_of = _compute_fred_zscore36(
        source_series_id="BAA10YM",
        as_of_timestamp=as_of_dt,
        api_key=fred_api_key,
    )
    series_payloads["us_credit_spread_z36"] = _build_fred_runtime_payload(
        source_series_id="BAA10YM",
        adapter="fred",
        official_source="Moody's/Federal Reserve via FRED",
        observation_date=us_credit_as_of,
        release_date=cutoff_dt,
        retrieval_timestamp=retrieval_timestamp,
        transformation_method="zscore36_3mma",
        value=us_credit_value,
    )

    try:
        us_imports_value, us_imports_as_of = _compute_fred_yoy_3obs_mean(
            source_series_id="A255RO1Q156NBEA",
            as_of_timestamp=as_of_dt,
            api_key=fred_api_key,
        )
        series_payloads["us_real_imports_goods_yoy_3mma"] = _build_fred_runtime_payload(
            source_series_id="A255RO1Q156NBEA",
            adapter="fred",
            official_source="BEA via FRED",
            observation_date=us_imports_as_of,
            release_date=cutoff_dt,
            retrieval_timestamp=retrieval_timestamp,
            transformation_method="yoy_3obs_mean",
            value=us_imports_value,
        )
    except Exception as exc:
        degraded_mode = True
        warning_flags_by_series["us_real_pce_goods_yoy_3mma"] = (
            f"us_real_imports_goods_live_fetch_failed:{exc.__class__.__name__}",
        )
        confidence_by_series["us_real_pce_goods_yoy_3mma"] = 0.6
        us_pce_value, us_pce_as_of = _compute_fred_yoy_3mma(
            source_series_id="DGDSRX1",
            as_of_timestamp=as_of_dt,
            api_key=fred_api_key,
        )
        series_payloads["us_real_pce_goods_yoy_3mma"] = _build_fred_runtime_payload(
            source_series_id="DGDSRX1",
            adapter="fred",
            official_source="BEA via FRED",
            observation_date=us_pce_as_of,
            release_date=cutoff_dt,
            retrieval_timestamp=retrieval_timestamp,
            transformation_method="yoy_3mma",
            value=us_pce_value,
        )

    broad_usd_value, broad_usd_as_of = _compute_fred_log_return_3m(
        source_series_id="TWEXBGSMTH",
        as_of_timestamp=as_of_dt,
        api_key=fred_api_key,
    )
    series_payloads["broad_usd_3m_log_return"] = _build_fred_runtime_payload(
        source_series_id="TWEXBGSMTH",
        adapter="fred",
        official_source="Federal Reserve via FRED",
        observation_date=broad_usd_as_of,
        release_date=cutoff_dt,
        retrieval_timestamp=retrieval_timestamp,
        transformation_method="log_return_3m",
        value=broad_usd_value,
    )

    return build_live_macro_data_source_from_provider_payloads(
        series_payloads,
        degraded_mode=degraded_mode,
        source_name=source_name,
        source_version=source_version,
        confidence_by_series=confidence_by_series,
        warning_flags_by_series=warning_flags_by_series,
    )


def _require_api_key(env_name: str) -> str:
    api_key = os.getenv(env_name, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing macro provider auth key env: {env_name}")
    return api_key


def _build_ecos_runtime_payload(
    *,
    table_code: str,
    item_codes: Sequence[str],
    observation_date: datetime,
    release_date: datetime,
    retrieval_timestamp: str,
    transformation_method: str,
    value: float,
) -> dict[str, Any]:
    return {
        "provider": "ecos",
        "service": "StatisticSearch",
        "series": [
            {
                "table_code": table_code,
                "item_code": item_codes[0],
                "observation_date": observation_date.strftime("%Y-%m"),
                "release_date": release_date.date().isoformat(),
                "retrieval_timestamp": retrieval_timestamp,
                "transformation_method": transformation_method,
                "value": f"{value:.6f}",
            }
        ],
    }


def _build_fred_runtime_payload(
    *,
    source_series_id: str,
    adapter: str,
    official_source: str,
    observation_date: datetime,
    release_date: datetime,
    retrieval_timestamp: str,
    transformation_method: str,
    value: float,
) -> dict[str, Any]:
    return {
        "provider": "us_macro",
        "adapter": adapter,
        "official_source": official_source,
        "series": [
            {
                "series_id": source_series_id,
                "observation_date": observation_date.date().isoformat(),
                "release_date": release_date.date().isoformat(),
                "retrieval_timestamp": retrieval_timestamp,
                "transformation_method": transformation_method,
                "value": f"{value:.6f}",
            }
        ],
    }


def _compute_ecos_yoy_3mma(
    *,
    table_code: str,
    item_codes: Sequence[str],
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    rows = _fetch_ecos_rows(
        table_code=table_code,
        item_codes=item_codes,
        frequency="M",
        start_period=_format_month(_shift_months(as_of_timestamp, -20)),
        end_period=_format_month(as_of_timestamp),
        api_key=api_key,
    )
    points = _ecos_rows_to_points(rows)
    value = _latest_yoy_moving_average(points, lag_periods=12, window_size=3)
    return value, points[-1][0]


def _compute_ecos_log_return_3m(
    *,
    table_code: str,
    item_codes: Sequence[str],
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    rows = _fetch_ecos_rows(
        table_code=table_code,
        item_codes=item_codes,
        frequency="M",
        start_period=_format_month(_shift_months(as_of_timestamp, -6)),
        end_period=_format_month(as_of_timestamp),
        api_key=api_key,
    )
    points = _ecos_rows_to_points(rows)
    value = _latest_log_return(points, lookback_periods=3)
    return value, points[-1][0]


def _compute_ecos_credit_spread_z36(
    *,
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    corp_rows = _fetch_ecos_rows(
        table_code="721Y001",
        item_codes=("7020000",),
        frequency="M",
        start_period=_format_month(_shift_months(as_of_timestamp, -48)),
        end_period=_format_month(as_of_timestamp),
        api_key=api_key,
    )
    gov_rows = _fetch_ecos_rows(
        table_code="721Y001",
        item_codes=("5020000",),
        frequency="M",
        start_period=_format_month(_shift_months(as_of_timestamp, -48)),
        end_period=_format_month(as_of_timestamp),
        api_key=api_key,
    )
    corp_points = _ecos_rows_to_points(corp_rows)
    gov_points = _ecos_rows_to_points(gov_rows)
    spread_points = _subtract_series(corp_points, gov_points)
    value = _latest_zscore(spread_points, lookback_periods=36, smooth_window=3)
    return value, spread_points[-1][0]


def _compute_fred_yoy_3mma(
    *,
    source_series_id: str,
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    observations = _fetch_fred_observations(
        source_series_id=source_series_id,
        observation_start=_format_date(_shift_months(as_of_timestamp, -20)),
        observation_end=_format_date(as_of_timestamp),
        api_key=api_key,
    )
    points = _fred_observations_to_points(observations)
    value = _latest_yoy_moving_average(points, lag_periods=12, window_size=3)
    return value, points[-1][0]


def _compute_fred_log_return_3m(
    *,
    source_series_id: str,
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    observations = _fetch_fred_observations(
        source_series_id=source_series_id,
        observation_start=_format_date(_shift_months(as_of_timestamp, -6)),
        observation_end=_format_date(as_of_timestamp),
        api_key=api_key,
    )
    points = _fred_observations_to_points(observations)
    value = _latest_log_return(points, lookback_periods=3)
    return value, points[-1][0]


def _compute_fred_zscore36(
    *,
    source_series_id: str,
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    observations = _fetch_fred_observations(
        source_series_id=source_series_id,
        observation_start=_format_date(_shift_months(as_of_timestamp, -48)),
        observation_end=_format_date(as_of_timestamp),
        api_key=api_key,
    )
    points = _fred_observations_to_points(observations)
    value = _latest_zscore(points, lookback_periods=36, smooth_window=3)
    return value, points[-1][0]


def _compute_fred_yoy_3obs_mean(
    *,
    source_series_id: str,
    as_of_timestamp: datetime,
    api_key: str,
) -> tuple[float, datetime]:
    observations = _fetch_fred_observations(
        source_series_id=source_series_id,
        observation_start=_format_date(_shift_months(as_of_timestamp, -36)),
        observation_end=_format_date(as_of_timestamp),
        api_key=api_key,
    )
    points = _fred_observations_to_points(observations)
    value = _latest_average(points, window_size=3)
    return value, points[-1][0]


def _fetch_ecos_rows(
    *,
    table_code: str,
    item_codes: Sequence[str],
    frequency: str,
    start_period: str,
    end_period: str,
    api_key: str,
) -> list[Mapping[str, Any]]:
    path_parts = [
        ECOS_API_BASE_URL,
        api_key,
        "json",
        "kr",
        "1",
        "1000",
        table_code,
        frequency,
        start_period,
        end_period,
        *[str(code) for code in item_codes],
    ]
    url = "/".join(part.strip("/") for part in path_parts)
    with httpx.Client(timeout=20.0) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("StatisticSearch", {}).get("row", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"ECOS series returned no rows: {table_code}:{'/'.join(item_codes)}")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _fetch_fred_observations(
    *,
    source_series_id: str,
    observation_start: str,
    observation_end: str,
    api_key: str,
) -> list[Mapping[str, Any]]:
    params = {
        "series_id": source_series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": observation_start,
        "observation_end": observation_end,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.get(FRED_OBSERVATIONS_API_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    observations = payload.get("observations", [])
    if not isinstance(observations, list) or not observations:
        raise ValueError(f"FRED series returned no observations: {source_series_id}")
    return [dict(item) for item in observations if isinstance(item, Mapping)]


def _ecos_rows_to_points(rows: Sequence[Mapping[str, Any]]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for row in rows:
        raw_value = row.get("DATA_VALUE")
        if raw_value in (None, ""):
            continue
        points.append((_parse_ecos_time(str(row.get("TIME") or "")), float(str(raw_value))))
    if not points:
        raise ValueError("ECOS series rows contained no numeric values")
    return sorted(points, key=lambda item: item[0])


def _fred_observations_to_points(
    observations: Sequence[Mapping[str, Any]],
) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for observation in observations:
        raw_value = observation.get("value")
        if raw_value in (None, "", "."):
            continue
        points.append(
            (parse_datetime(f"{observation['date']}T00:00:00"), float(str(raw_value)))
        )
    if not points:
        raise ValueError("FRED observations contained no numeric values")
    return sorted(points, key=lambda item: item[0])


def _latest_yoy_moving_average(
    points: Sequence[tuple[datetime, float]],
    *,
    lag_periods: int,
    window_size: int,
) -> float:
    if len(points) <= lag_periods:
        raise ValueError("not enough observations to compute YoY")
    yoy_values: list[float] = []
    for index in range(lag_periods, len(points)):
        prior_value = points[index - lag_periods][1]
        current_value = points[index][1]
        if prior_value == 0:
            continue
        yoy_values.append(((current_value / prior_value) - 1.0) * 100.0)
    if len(yoy_values) < window_size:
        raise ValueError("not enough YoY observations to compute moving average")
    return sum(yoy_values[-window_size:]) / window_size


def _latest_average(points: Sequence[tuple[datetime, float]], *, window_size: int) -> float:
    if len(points) < window_size:
        raise ValueError("not enough observations to compute rolling average")
    values = [point[1] for point in points[-window_size:]]
    return sum(values) / window_size


def _latest_log_return(
    points: Sequence[tuple[datetime, float]],
    *,
    lookback_periods: int,
) -> float:
    if len(points) <= lookback_periods:
        raise ValueError("not enough observations to compute log return")
    start_value = points[-(lookback_periods + 1)][1]
    end_value = points[-1][1]
    if start_value <= 0 or end_value <= 0:
        raise ValueError("log return requires positive observation values")
    return math.log(end_value / start_value) * 100.0


def _latest_zscore(
    points: Sequence[tuple[datetime, float]],
    *,
    lookback_periods: int,
    smooth_window: int,
) -> float:
    if len(points) < lookback_periods:
        raise ValueError("not enough observations to compute z-score")
    smoothed_values = _rolling_mean([point[1] for point in points], smooth_window)
    if len(smoothed_values) < lookback_periods:
        raise ValueError("not enough smoothed observations to compute z-score")
    window = smoothed_values[-lookback_periods:]
    mean_value = sum(window) / len(window)
    variance = sum((value - mean_value) ** 2 for value in window) / len(window)
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0
    return (window[-1] - mean_value) / std_dev


def _rolling_mean(values: Sequence[float], window_size: int) -> list[float]:
    if window_size <= 0:
        raise ValueError("window_size must be positive")
    if len(values) < window_size:
        return []
    means: list[float] = []
    for index in range(window_size - 1, len(values)):
        window = values[index - window_size + 1 : index + 1]
        means.append(sum(window) / window_size)
    return means


def _subtract_series(
    left_points: Sequence[tuple[datetime, float]],
    right_points: Sequence[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    right_by_date = {point[0]: point[1] for point in right_points}
    spread_points = [
        (left_dt, left_value - right_by_date[left_dt])
        for left_dt, left_value in left_points
        if left_dt in right_by_date
    ]
    if not spread_points:
        raise ValueError("series do not overlap for spread calculation")
    return spread_points


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = (value.year * 12 + (value.month - 1)) + months
    year = month_index // 12
    month = (month_index % 12) + 1
    return value.replace(year=year, month=month, day=1)


def _format_month(value: datetime) -> str:
    return value.strftime("%Y%m")


def _format_date(value: datetime) -> str:
    return value.date().isoformat()


def _parse_ecos_time(value: str) -> datetime:
    text = value.strip()
    if len(text) == 6:
        return parse_datetime(f"{text[:4]}-{text[4:6]}-01T00:00:00")
    if len(text) == 4:
        return parse_datetime(f"{text}-01-01T00:00:00")
    return parse_datetime(text)
