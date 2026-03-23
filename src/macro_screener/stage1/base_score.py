from __future__ import annotations


def rank_to_score(rank: int, total: int) -> float:
    """순위를 점수로 변환한다."""
    if total <= 0:
        raise ValueError("total ranked industries must be positive")
    if rank < 1 or rank > total:
        raise ValueError(f"rank must be within 1..{total}, got {rank}")
    if total == 1:
        return 0.0
    if total == 2:
        return 1.0 if rank == 1 else -1.0

    lower_mid = (total + 1) // 2
    upper_mid = (total + 2) // 2
    if rank < lower_mid:
        return float((lower_mid - rank) / max(lower_mid - 1, 1))
    if rank <= upper_mid:
        return 0.0
    return float(-(rank - upper_mid) / max(total - upper_mid, 1))


def channel_contribution_map(
    exposures: dict[str, int],
    channel_states: dict[str, int],
    *,
    channels: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX"),
) -> dict[str, float]:
    """채널별 기여도 맵을 만든다."""
    return {
        channel: float(exposures.get(channel, 0) * channel_states.get(channel, 0))
        for channel in channels
    }


def sum_contributions(
    exposures: dict[str, int],
    channel_states: dict[str, int],
    *,
    channels: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX"),
) -> tuple[float, float, float]:
    """기여도 합계를 계산한다."""
    contribution_map = channel_contribution_map(
        exposures,
        channel_states,
        channels=channels,
    )
    base_score = 0.0
    negative_penalty = 0.0
    positive_contribution = 0.0
    for channel in channels:
        contribution = contribution_map[channel]
        base_score += contribution
        if contribution < 0:
            negative_penalty += abs(contribution)
        elif contribution > 0:
            positive_contribution += contribution
    return base_score, negative_penalty, positive_contribution


def summarize_weighted_contributions(
    contributions: dict[str, float],
) -> tuple[float, float, float]:
    """가중 기여도를 요약한다."""
    base_score = sum(contributions.values())
    negative_penalty = sum(abs(value) for value in contributions.values() if value < 0)
    positive_contribution = sum(value for value in contributions.values() if value > 0)
    return float(base_score), float(negative_penalty), float(positive_contribution)
