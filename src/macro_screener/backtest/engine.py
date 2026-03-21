from __future__ import annotations

from typing import Any

from macro_screener.backtest.calendar import iter_trading_dates
from macro_screener.backtest.snapshot_store import build_backtest_output_dir
from macro_screener.pipeline.runner import run_demo

DEFAULT_BACKTEST_RUN_TYPE = "post_close"


def build_backtest_stub_plan(
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
) -> list[dict[str, str]]:
    plans: list[dict[str, str]] = []
    for trading_date in iter_trading_dates(start_date, end_date):
        plans.append(
            {
                "run_id": f"{trading_date}-{run_type}",
                "run_type": run_type,
                "trading_date": trading_date,
                "as_of_timestamp": f"{trading_date}T15:45:00+09:00",
                "input_cutoff": f"{trading_date}T15:45:00+09:00",
                "published_at": f"{trading_date}T15:45:00+09:00",
            }
        )
    return plans


def run_backtest_stub(
    output_dir: str,
    *,
    start_date: str,
    end_date: str,
    run_type: str = DEFAULT_BACKTEST_RUN_TYPE,
) -> dict[str, Any]:
    plan = build_backtest_stub_plan(start_date=start_date, end_date=end_date, run_type=run_type)
    backtest_root = build_backtest_output_dir(
        output_dir, start_date=start_date, end_date=end_date, run_type=run_type
    )
    runs = []
    for context in plan:
        result = run_demo(
            backtest_root,
            run_id=context["run_id"],
            run_type=context["run_type"],
            as_of_timestamp=context["as_of_timestamp"],
            input_cutoff=context["input_cutoff"],
            published_at=context["published_at"],
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
    }
