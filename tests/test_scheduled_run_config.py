from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from macro_screener.backtest.calendar import is_trading_day
from macro_screener.config import load_config
from macro_screener.models import RunMode
from macro_screener.pipeline.runner import _enforce_macro_source_policy
from macro_screener.pipeline.scheduler import SCHEDULED_RUN_TIMES, build_scheduled_context


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_post_close_context_uses_1800_kst() -> None:
    context = build_scheduled_context(
        "2026-03-27",
        "post_close",
        attempted_at="2026-03-27T18:00:00+09:00",
    )

    assert SCHEDULED_RUN_TIMES["post_close"] == "18:00:00+09:00"
    assert context["as_of_timestamp"] == "2026-03-27T18:00:00+09:00"
    assert context["input_cutoff"] == "2026-03-27T18:00:00+09:00"


def test_github_actions_schedule_matches_requested_kst_windows() -> None:
    workflow_path = _repo_root() / ".github" / "workflows" / "scheduled-run.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    on_config = workflow.get("on", workflow.get(True))

    assert workflow["name"] == "scheduled-run"
    assert on_config["schedule"] == [
        {"cron": "30 23 * * 0-4"},
        {"cron": "0 9 * * 1-5"},
    ]

    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert '--config config/github-actions.yaml' in workflow_text
    assert 'RUN_TYPE="pre_open"' in workflow_text
    assert 'RUN_TYPE="post_close"' in workflow_text
    assert 'TZ=Asia/Seoul date +%F' in workflow_text
    assert (
        'IS_TRADING_DAY="$(TRADING_DATE="$TRADING_DATE" PYTHONPATH=src:. python3 -c'
        in workflow_text
    )
    assert "if: env.IS_TRADING_DAY == 'true'" in workflow_text
    assert "if: env.IS_TRADING_DAY != 'true'" in workflow_text
    assert 'Skipping scheduled run for non-trading day' in workflow_text


def test_non_trading_day_detection_matches_workflow_guard() -> None:
    assert is_trading_day(date(2026, 3, 27)) is True
    assert is_trading_day(date(2026, 1, 1)) is False


def test_github_actions_config_allows_last_known_live_fallback() -> None:
    default_config = load_config()
    github_actions_config = load_config(_repo_root() / 'config' / 'github-actions.yaml')
    macro_result = SimpleNamespace(
        source_name='ecos_fred_live', fallback_mode='last_known_channel_states'
    )

    with pytest.raises(RuntimeError, match='last_known_macro_fallback_requires_degraded_mode'):
        _enforce_macro_source_policy(
            config=default_config,
            mode=RunMode.SCHEDULED,
            macro_result=macro_result,
            channel_states=None,
            macro_source=None,
            use_demo_inputs=False,
        )

    _enforce_macro_source_policy(
        config=github_actions_config,
        mode=RunMode.SCHEDULED,
        macro_result=macro_result,
        channel_states=None,
        macro_source=None,
        use_demo_inputs=False,
    )
