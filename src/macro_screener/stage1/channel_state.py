from __future__ import annotations

from datetime import datetime

from macro_screener.models import ChannelState

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")


def build_channel_state_records(
    channel_states: dict[str, int],
    *,
    effective_at: datetime,
    as_of_timestamp: datetime | None = None,
    input_cutoff: datetime | None = None,
    source_name: str = "manual",
    source_version: str | None = None,
    confidence_by_channel: dict[str, float] | None = None,
    fallback_mode: str | None = None,
    warning_flags_by_channel: dict[str, list[str]] | None = None,
) -> list[ChannelState]:
    missing = [channel for channel in CHANNELS if channel not in channel_states]
    if missing:
        raise ValueError(f"missing channel states: {', '.join(missing)}")
    resolved_as_of = as_of_timestamp or effective_at
    resolved_cutoff = input_cutoff or resolved_as_of
    confidence_map = confidence_by_channel or {}
    warning_map = warning_flags_by_channel or {}
    return [
        ChannelState(
            channel=channel,
            state=channel_states[channel],
            effective_at=effective_at,
            as_of_timestamp=resolved_as_of,
            input_cutoff=resolved_cutoff,
            source_name=source_name,
            source_version=source_version,
            confidence=confidence_map.get(channel),
            fallback_mode=fallback_mode,
            warning_flags=list(warning_map.get(channel, [])),
        )
        for channel in CHANNELS
    ]
