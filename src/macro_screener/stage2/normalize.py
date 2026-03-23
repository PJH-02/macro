from __future__ import annotations

import math


def zscore(values: list[float]) -> list[float]:
    """표준점수 시퀀스를 계산한다."""
    if not values:
        return []
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    if variance == 0.0:
        return [0.0 for _ in values]
    stddev = math.sqrt(variance)
    return [round((value - mean) / stddev, 6) for value in values]
