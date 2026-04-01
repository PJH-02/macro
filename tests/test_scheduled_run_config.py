from __future__ import annotations

from pathlib import Path

import yaml

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
    assert 'RUN_TYPE="pre_open"' in workflow_text
    assert 'RUN_TYPE="post_close"' in workflow_text
    assert 'TZ=Asia/Seoul date +%F' in workflow_text
