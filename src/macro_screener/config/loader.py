from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from macro_screener.config.defaults import DEFAULT_CONFIG
from macro_screener.config.types import AppConfig


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """deep merge을 처리한다."""
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def default_config_path(base_path: Path | None = None) -> Path:
    """default 설정 경로을 처리한다."""
    root = base_path or Path.cwd()
    return root / "config" / "default.yaml"


def default_env_path(base_path: Path | None = None) -> Path:
    """default 환경 경로을 처리한다."""
    root = base_path or Path.cwd()
    return root / ".env"


def load_env_file(path: Path | str | None = None, *, override: bool = False) -> None:
    """환경 파일을 불러온다"""
    env_path = Path(path) if path is not None else default_env_path()
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def load_config(path: Path | str | None = None) -> AppConfig:
    """설정을 불러온다"""
    load_env_file()
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
