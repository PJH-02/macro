from __future__ import annotations


def sum_contributions(
    exposures: dict[str, int],
    channel_states: dict[str, int],
    *,
    channels: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX"),
) -> tuple[float, float, float]:
    base_score = 0.0
    negative_penalty = 0.0
    positive_contribution = 0.0
    for channel in channels:
        contribution = float(exposures.get(channel, 0) * channel_states.get(channel, 0))
        base_score += contribution
        if contribution < 0:
            negative_penalty += abs(contribution)
        elif contribution > 0:
            positive_contribution += contribution
    return base_score, negative_penalty, positive_contribution
