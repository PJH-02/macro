from __future__ import annotations

from macro_screener import cli


def test_format_command_output_summarizes_snapshot_result() -> None:
    result = {
        "snapshot": {
            "run_id": "manual-run-1",
            "run_type": "manual",
            "status": "published",
            "industry_scores": [{"industry_code": "AUTO"}],
            "stock_scores": [{"stock_code": "005930"}, {"stock_code": "000660"}],
        },
        "latest": {
            "snapshot_json": "/tmp/snapshot.json",
            "screened_stock_csv": "/tmp/screened_stock_list.csv",
            "screened_stocks_by_industry_json": "/tmp/screened_stocks_by_industry.json",
            "industry_csv": "/tmp/industry_scores.csv",
        },
        "warnings": ["stale_input"],
    }

    payload = cli._format_command_output("manual-run", result)

    assert payload["command"] == "manual-run"
    assert payload["snapshot"] is result["snapshot"]
    assert payload["summary"] == {
        "run_id": "manual-run-1",
        "run_type": "manual",
        "status": "published",
        "industry_count": 1,
        "stock_count": 2,
        "warning_count": 1,
    }
    assert payload["artifacts"]["screened_stock_csv"] == "/tmp/screened_stock_list.csv"
    assert payload["warnings"] == ["stale_input"]


def test_format_command_output_summarizes_backtest_result() -> None:
    result = {
        "output_dir": "/tmp/backtest",
        "run_type": "pre_open",
        "trading_dates": ["2026-03-03", "2026-03-04", "2026-03-05"],
        "runs": [
            {"run_id": "r1", "status": "published", "trading_date": "2026-03-03"},
            {"run_id": "r2", "status": "incomplete", "trading_date": "2026-03-04"},
            {"run_id": "r3", "status": "published", "trading_date": "2026-03-05"},
        ],
        "generated_at": "2026-03-23T07:00:00",
    }

    payload = cli._format_command_output("backtest-run", result)

    assert payload["summary"] == {
        "output_dir": "/tmp/backtest",
        "run_type": "pre_open",
        "trading_date_count": 3,
        "run_count": 3,
        "published_count": 2,
        "incomplete_count": 1,
        "failed_count": 0,
    }
    assert payload["warnings"] == []
    assert payload["trading_dates"] == ["2026-03-03", "2026-03-04", "2026-03-05"]


def test_format_command_output_summarizes_show_config_result() -> None:
    config_payload = {
        "config_version": "mvp-1",
        "environment": "production",
        "runtime": {"normal_mode": "live"},
        "universe": {"markets": ["KOSPI", "KOSDAQ"]},
    }

    payload = cli._format_command_output("show-config", config_payload)

    assert payload["summary"] == {
        "config_version": "mvp-1",
        "environment": "production",
        "normal_mode": "live",
        "market_count": 2,
    }
    assert payload["config_version"] == "mvp-1"
