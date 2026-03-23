from __future__ import annotations

DEFAULT_OVERLAYS: dict[str, float] = {"AUTO": 0.2, "SHIP": 0.1, "PHARMA": 0.0}


def resolve_overlay_adjustments(overrides: dict[str, float] | None = None) -> dict[str, float]:
    """오버레이 보정값을 확정한다."""
    base = dict(DEFAULT_OVERLAYS)
    if overrides:
        base.update({key: float(value) for key, value in overrides.items()})
    return base
