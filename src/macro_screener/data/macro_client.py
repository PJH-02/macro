from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from macro_screener.db import SnapshotRegistry
from macro_screener.models import ChannelState

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
