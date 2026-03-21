from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from macro_screener.config import AppConfig
from macro_screener.db.store import SnapshotRegistry


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    created_directories: tuple[Path, ...]


def bootstrap_runtime(config: AppConfig, base_path: Path) -> BootstrapResult:
    directories = (
        config.paths.resolve(config.paths.data_dir, base_path),
        config.paths.resolve(config.paths.log_dir, base_path),
        config.paths.resolve(config.paths.snapshot_dir, base_path),
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    SnapshotRegistry.for_config(config=config, base_path=base_path).initialize()
    return BootstrapResult(created_directories=directories)
