"""Minimal deterministic MVP helpers for the macro screener."""

from .contracts import IndustryScore, Snapshot, Stage1Result, StockScore
from .mvp import (
    CHANNELS,
    DEFAULT_BACKTEST_RUN_TYPE,
    DEFAULT_DEMO_AS_OF,
    DEFAULT_DEMO_INPUT_CUTOFF,
    DEFAULT_DEMO_RUN_ID,
    DEFAULT_DEMO_RUN_TYPE,
    build_backtest_stub_plan,
    build_scheduled_stub_context,
    classify_disclosure,
    compute_stage1_result,
    compute_stock_scores,
    publish_snapshot,
    run_backtest_stub,
    run_demo,
    run_scheduled_stub,
)

__all__ = [
    "CHANNELS",
    "DEFAULT_BACKTEST_RUN_TYPE",
    "DEFAULT_DEMO_AS_OF",
    "DEFAULT_DEMO_INPUT_CUTOFF",
    "DEFAULT_DEMO_RUN_ID",
    "DEFAULT_DEMO_RUN_TYPE",
    "IndustryScore",
    "Snapshot",
    "Stage1Result",
    "StockScore",
    "build_backtest_stub_plan",
    "build_scheduled_stub_context",
    "classify_disclosure",
    "compute_stage1_result",
    "compute_stock_scores",
    "publish_snapshot",
    "run_backtest_stub",
    "run_demo",
    "run_scheduled_stub",
]
