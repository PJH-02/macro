from __future__ import annotations

import math

BLOCK_WEIGHTS = {
    "supply_contract": 1.0,
    "treasury_stock": 0.8,
    "facility_investment": 0.6,
    "dilutive_financing": -1.0,
    "correction_cancellation_withdrawal": -0.7,
    "governance_risk": -0.9,
    "neutral": 0.0,
}

HALF_LIVES = {
    "supply_contract": 20,
    "treasury_stock": 10,
    "facility_investment": 60,
    "dilutive_financing": 60,
    "correction_cancellation_withdrawal": 10,
    "governance_risk": 120,
}


def decayed_score(block_name: str, trading_days_elapsed: int) -> float:
    weight = BLOCK_WEIGHTS[block_name]
    if weight == 0.0:
        return 0.0
    half_life = HALF_LIVES[block_name]
    decay = math.exp(-math.log(2) * max(trading_days_elapsed, 0) / half_life)
    return weight * decay
