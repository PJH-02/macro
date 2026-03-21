from __future__ import annotations

from pathlib import Path


def build_backtest_output_dir(
    output_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    run_type: str,
) -> Path:
    return Path(output_dir) / "backtest" / f"{start_date}_{end_date}_{run_type}"
