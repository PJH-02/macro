from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from macro_screener.config.defaults import DEFAULT_CONFIG
from macro_screener.config.types import AppConfig


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def default_config_path(base_path: Path | None = None) -> Path:
    root = base_path or Path.cwd()
    return root / "config" / "default.yaml"


def load_config(path: Path | str | None = None) -> AppConfig:
    config_path = Path(path) if path is not None else default_config_path()
    loaded: dict[str, Any] = {}

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or {}
        if not isinstance(parsed, dict):
            raise ValueError("Config file must contain a top-level mapping.")
        loaded = parsed

    merged = deep_merge(DEFAULT_CONFIG, loaded)
    return AppConfig.from_dict(merged)
