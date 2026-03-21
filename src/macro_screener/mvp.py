from __future__ import annotations

from macro_screener.backtest import (
    DEFAULT_BACKTEST_RUN_TYPE,
    build_backtest_plan,
    build_backtest_stub_plan,
    run_backtest,
    run_backtest_stub,
)
from macro_screener.data.dart_client import DEFAULT_DISCLOSURES
from macro_screener.data.krx_client import DEFAULT_EXPOSURES, DEFAULT_STOCKS
from macro_screener.data.macro_client import CHANNELS, DEFAULT_CHANNEL_STATES
from macro_screener.pipeline import (
    DEFAULT_CONFIG_VERSION,
    DEFAULT_DEMO_AS_OF,
    DEFAULT_DEMO_INPUT_CUTOFF,
    DEFAULT_DEMO_RUN_ID,
    DEFAULT_DEMO_RUN_TYPE,
    SCHEDULED_RUN_TIMES,
    build_demo_snapshot,
    build_manual_context,
    build_scheduled_context,
    publish_snapshot,
    run_demo,
    run_manual,
    run_scheduled,
    run_scheduled_stub,
    scheduled_window_key,
)
from macro_screener.stage1 import DEFAULT_OVERLAYS, compute_stage1_result
from macro_screener.stage2 import (
    BLOCK_WEIGHTS,
    DEFAULT_LAMBDA,
    HALF_LIVES,
    classify_disclosure,
    compute_stock_scores,
)

__all__ = [
    "BLOCK_WEIGHTS",
    "CHANNELS",
    "DEFAULT_BACKTEST_RUN_TYPE",
    "DEFAULT_CONFIG_VERSION",
    "DEFAULT_DEMO_AS_OF",
    "DEFAULT_DEMO_INPUT_CUTOFF",
    "DEFAULT_DEMO_RUN_ID",
    "DEFAULT_DEMO_RUN_TYPE",
    "DEFAULT_CHANNEL_STATES",
    "DEFAULT_DISCLOSURES",
    "DEFAULT_EXPOSURES",
    "DEFAULT_LAMBDA",
    "DEFAULT_OVERLAYS",
    "DEFAULT_STOCKS",
    "HALF_LIVES",
    "SCHEDULED_RUN_TIMES",
    "build_backtest_plan",
    "build_backtest_stub_plan",
    "build_demo_snapshot",
    "build_manual_context",
    "build_scheduled_context",
    "classify_disclosure",
    "compute_stage1_result",
    "compute_stock_scores",
    "publish_snapshot",
    "run_backtest",
    "run_backtest_stub",
    "run_demo",
    "run_manual",
    "run_scheduled",
    "run_scheduled_stub",
    "scheduled_window_key",
]


def build_scheduled_stub_context(
    trading_date: str, run_type: str
) -> dict[str, str | dict[str, str]]:
    return build_scheduled_context(trading_date, run_type)
