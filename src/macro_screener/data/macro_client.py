from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence

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
class LiveMacroDataSource:
    channel_signals: Mapping[str, Sequence[MacroSeriesSignal]]
    source_name: str = "live_macro"
    source_version: str | None = None

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


def _parse_series_timestamp(value: str) -> datetime:
    text = value.strip()
    if len(text) == 7:
        text = f"{text}-01T00:00:00"
    elif len(text) == 10:
        text = f"{text}T00:00:00"
    return parse_datetime(text)


def _dedupe_flags(flags: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(flag) for flag in flags if str(flag).strip()))
