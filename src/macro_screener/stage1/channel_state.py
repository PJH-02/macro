from __future__ import annotations

from datetime import datetime

from macro_screener.models import ChannelState

CHANNELS: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")


def build_channel_state_records(
    channel_states: dict[str, int],
    *,
    effective_at: datetime,
    source: str = "manual",
) -> list[ChannelState]:
    missing = [channel for channel in CHANNELS if channel not in channel_states]
    if missing:
        raise ValueError(f"missing channel states: {', '.join(missing)}")
    return [
        ChannelState(
            channel=channel,
            state=channel_states[channel],
            effective_at=effective_at,
            source=source,
        )
        for channel in CHANNELS
    ]
