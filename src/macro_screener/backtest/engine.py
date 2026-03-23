from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from macro_screener.backtest.calendar import iter_trading_dates, previous_trading_day
from macro_screener.backtest.snapshot_store import build_backtest_output_dir
from macro_screener.models import RunMode
from macro_screener.pipeline.runner import run_pipeline_context
from macro_screener.pipeline.scheduler import SCHEDULED_RUN_TIMES

DEFAULT_BACKTEST_RUN_TYPE = "post_close"


def build_backtest_plan(
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
    batch_id: str | None = None,
) -> list[dict[str, str]]:
    """백테스트 실행 계획을 구성한다."""
    batch_token = batch_id or f"backtest-{start_date}-{end_date}-{run_type}"
    plans: list[dict[str, str]] = []
    for trading_date in iter_trading_dates(start_date, end_date):
        as_of_timestamp = f"{trading_date}T{SCHEDULED_RUN_TIMES[run_type]}"
        previous_close_cutoff = (
            previous_trading_day(datetime.fromisoformat(trading_date).date()).isoformat()
        )
        input_cutoff = (
            f"{trading_date}T15:45:00+09:00"
            if run_type == "post_close"
            else f"{previous_close_cutoff}T18:00:00+09:00"
        )
        plans.append(
            {
                "run_id": f"{batch_token}-{trading_date}-{run_type}",
                "run_type": run_type,
                "trading_date": trading_date,
                "as_of_timestamp": as_of_timestamp,
                "input_cutoff": input_cutoff,
                "published_at": as_of_timestamp,
            }
        )
    return plans


def build_backtest_stub_plan(
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
) -> list[dict[str, str]]:
    """백테스트 스텁 실행 계획을 구성한다."""
    return build_backtest_plan(start_date=start_date, end_date=end_date, run_type=run_type)


def run_backtest(
    output_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """백테스트를 실행한다."""
    plan = build_backtest_plan(start_date=start_date, end_date=end_date, run_type=run_type)
    backtest_root = build_backtest_output_dir(
        output_dir, start_date=start_date, end_date=end_date, run_type=run_type
    )
    runs = []
    for context in plan:
        result = run_pipeline_context(
            backtest_root,
            context=context,
            mode=RunMode.BACKTEST,
            config_path=config_path,
        )
        runs.append(
            {
                "run_id": context["run_id"],
                "trading_date": context["trading_date"],
                "status": result["snapshot"]["status"],
            }
        )
    return {
        "output_dir": str(backtest_root),
        "run_type": run_type,
        "trading_dates": [context["trading_date"] for context in plan],
        "runs": runs,
        "generated_at": datetime.now().isoformat(),
    }


def run_backtest_stub(
    output_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """백테스트 스텁을 실행한다."""
    return run_backtest(
        output_dir,
        start_date=start_date,
        end_date=end_date,
        run_type=run_type,
        config_path=config_path,
    )
