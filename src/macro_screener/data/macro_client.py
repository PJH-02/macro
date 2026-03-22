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
        states = self.store.load_last_channel_states()
        if not states:
            raise ValueError("no persisted macro channel states available")
        return MacroLoadResult(
            channel_states={state.channel: state.state for state in states},
            source_name="last_known",
            warnings=["macro_source_unavailable_using_last_known_channel_states"],
            fallback_mode="last_known_channel_states",
            warning_flags_by_channel={
                channel: ["macro_source_unavailable_using_last_known_channel_states"]
                for channel in CHANNELS
            },
        )


def last_known_channel_states(store: SnapshotRegistry) -> list[ChannelState] | None:
    return store.load_last_channel_states()
