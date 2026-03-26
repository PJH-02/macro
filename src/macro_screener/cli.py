from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import load_config
from .config.loader import repo_root
from .mvp import (
    DEFAULT_BACKTEST_RUN_TYPE,
    DEFAULT_DEMO_AS_OF,
    DEFAULT_DEMO_INPUT_CUTOFF,
    DEFAULT_DEMO_RUN_ID,
    DEFAULT_DEMO_RUN_TYPE,
    run_backtest,
    run_backtest_stub,
    run_demo,
    run_manual,
    run_scheduled,
)

CLICommandHandler = Callable[[argparse.Namespace], Any]
DEFAULT_CLI_OUTPUT_DIR = repo_root() / "src"


def _parse_channel_overrides(values: list[str]) -> dict[str, int]:
    """채널 overrides을 파싱한다"""
    overrides: dict[str, int] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid channel override: {item}")
        key, raw_value = item.split("=", 1)
        overrides[key.strip()] = int(raw_value.strip())
    return overrides


def _snapshot_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """스냅샷 요약을 처리한다."""
    snapshot = result.get("snapshot", {})
    warnings = result.get("warnings", [])
    if not isinstance(snapshot, Mapping):
        return {}
    sector_scores = snapshot.get("industry_scores", [])
    stock_scores = snapshot.get("stock_scores", [])
    return {
        "run_id": snapshot.get("run_id"),
        "run_type": snapshot.get("run_type"),
        "status": snapshot.get("status"),
        "industry_count": len(sector_scores) if isinstance(sector_scores, list) else 0,
        "stock_count": len(stock_scores) if isinstance(stock_scores, list) else 0,
        "warning_count": len(warnings) if isinstance(warnings, list) else 0,
    }


def _backtest_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """백테스트 요약을 처리한다."""
    runs = result.get("runs", [])
    run_list = runs if isinstance(runs, list) else []
    return {
        "output_dir": result.get("output_dir"),
        "run_type": result.get("run_type"),
        "trading_date_count": len(result.get("trading_dates", []))
        if isinstance(result.get("trading_dates", []), list)
        else 0,
        "run_count": len(run_list),
        "published_count": sum(1 for run in run_list if run.get("status") == "published"),
        "incomplete_count": sum(1 for run in run_list if run.get("status") == "incomplete"),
        "failed_count": sum(1 for run in run_list if run.get("status") == "failed"),
    }


def _config_summary(config_payload: Mapping[str, Any]) -> dict[str, Any]:
    """설정 요약을 처리한다."""
    runtime = config_payload.get("runtime", {})
    universe = config_payload.get("universe", {})
    markets = universe.get("markets", []) if isinstance(universe, Mapping) else []
    return {
        "config_version": config_payload.get("config_version"),
        "environment": config_payload.get("environment"),
        "normal_mode": runtime.get("normal_mode") if isinstance(runtime, Mapping) else None,
        "market_count": len(markets) if isinstance(markets, list) else 0,
    }


def _snapshot_artifacts(result: Mapping[str, Any]) -> dict[str, Any]:
    """스냅샷 산출물을 처리한다."""
    latest = result.get("latest", {})
    if not isinstance(latest, Mapping):
        return {}
    preferred_keys = (
        "snapshot_json",
        "screened_stock_csv",
        "screened_stocks_by_score_json",
        "screened_stocks_by_industry_json",
        "industry_csv",
        "industry_parquet",
        "stock_parquet",
    )
    return {key: latest[key] for key in preferred_keys if key in latest}


def _warnings_from_result(result: Mapping[str, Any]) -> list[Any]:
    """warnings from 결과을 처리한다."""
    warnings = result.get("warnings", [])
    return warnings if isinstance(warnings, list) else []


def _summary_for_command(command: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """요약 for 명령을 처리한다."""
    if command == "show-config":
        return _config_summary(result)
    if command in {"manual-run", "demo-run", "scheduled-run"}:
        return _snapshot_summary(result)
    if command in {"backtest-run", "backtest-stub"}:
        return _backtest_summary(result)
    return {}


def _format_command_output(command: str, result: Any) -> dict[str, Any]:
    """명령 출력을 문자열로 변환한다"""
    if not isinstance(result, Mapping):
        return {"command": command, "summary": {}, "warnings": [], "result": result}
    payload: dict[str, Any] = dict(result)
    payload["command"] = command
    payload["summary"] = _summary_for_command(command, result)
    payload.setdefault("warnings", _warnings_from_result(result))
    artifacts = _snapshot_artifacts(result)
    if artifacts:
        payload["artifacts"] = artifacts
    return payload


def _print_json(payload: Any) -> None:
    """출력 JSON을 처리한다."""
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _handle_show_config(args: argparse.Namespace) -> dict[str, Any]:
    """handle 표시 설정을 처리한다."""
    return load_config(args.config).to_dict()


def _handle_manual_run(args: argparse.Namespace) -> dict[str, Any]:
    """handle 수동 실행을 처리한다."""
    channel_states = _parse_channel_overrides(args.channel_state) if args.channel_state else None
    return run_manual(
        output_dir=args.output_dir,
        config_path=args.config,
        run_id=args.run_id,
        run_type=args.run_type,
        as_of_timestamp=args.as_of,
        input_cutoff=args.input_cutoff,
        published_at=args.published_at,
        channel_states=channel_states,
        macro_source=args.macro_source,
    )


def _handle_demo_run(args: argparse.Namespace) -> dict[str, Any]:
    """handle 데모 실행을 처리한다."""
    return run_demo(
        output_dir=args.output_dir,
        run_id=args.run_id,
        run_type=args.run_type,
        as_of_timestamp=args.as_of,
        input_cutoff=args.input_cutoff,
        published_at=args.published_at,
    )


def _handle_scheduled_run(args: argparse.Namespace) -> dict[str, Any]:
    """handle 스케줄 실행을 처리한다."""
    channel_states = _parse_channel_overrides(args.channel_state) if args.channel_state else None
    return run_scheduled(
        args.output_dir,
        trading_date=args.trading_date,
        run_type=args.run_type,
        attempted_at=args.attempted_at,
        channel_states=channel_states,
        macro_source=args.macro_source,
        config_path=args.config,
    )


def _handle_backtest_run(args: argparse.Namespace) -> dict[str, Any]:
    """handle 백테스트 실행을 처리한다."""
    return run_backtest(
        args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        run_type=args.run_type,
        config_path=args.config,
    )


def _handle_backtest_stub(args: argparse.Namespace) -> dict[str, Any]:
    """handle 백테스트 스텁을 처리한다."""
    return run_backtest_stub(
        args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        run_type=args.run_type,
        config_path=args.config,
    )


COMMAND_HANDLERS: dict[str, CLICommandHandler] = {
    "show-config": _handle_show_config,
    "manual-run": _handle_manual_run,
    "demo-run": _handle_demo_run,
    "scheduled-run": _handle_scheduled_run,
    "backtest-run": _handle_backtest_run,
    "backtest-stub": _handle_backtest_stub,
}


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        description="Macro screener CLI with machine-readable results and concise summaries"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_config = subparsers.add_parser(
        "show-config", help="print the effective config plus a short summary as JSON"
    )
    show_config.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional path to a YAML config file",
    )

    manual = subparsers.add_parser(
        "manual-run",
        help="run the manual pipeline and print a concise summary plus full JSON result",
    )
    manual.add_argument("--output-dir", type=Path, default=DEFAULT_CLI_OUTPUT_DIR)
    manual.add_argument("--config", type=Path, default=None)
    manual.add_argument("--run-id", default=None)
    manual.add_argument("--run-type", default=DEFAULT_DEMO_RUN_TYPE)
    manual.add_argument("--as-of", default=None)
    manual.add_argument("--input-cutoff", default=None)
    manual.add_argument("--published-at", default=None)
    manual.add_argument(
        "--macro-source",
        choices=("live", "manual"),
        default="live",
        help="select the macro-state source for this run",
    )
    manual.add_argument(
        "--channel-state",
        action="append",
        default=[],
        metavar="CHANNEL=VALUE",
        help="manual channel override, repeatable (e.g. G=1)",
    )

    demo = subparsers.add_parser(
        "demo-run",
        help="run the deterministic demo pipeline and print a concise summary plus full JSON",
    )
    demo.add_argument("--output-dir", type=Path, default=DEFAULT_CLI_OUTPUT_DIR)
    demo.add_argument("--run-id", default=DEFAULT_DEMO_RUN_ID)
    demo.add_argument("--run-type", default=DEFAULT_DEMO_RUN_TYPE)
    demo.add_argument("--as-of", default=DEFAULT_DEMO_AS_OF)
    demo.add_argument("--input-cutoff", default=DEFAULT_DEMO_INPUT_CUTOFF)
    demo.add_argument("--published-at", default=DEFAULT_DEMO_AS_OF)

    scheduled = subparsers.add_parser(
        "scheduled-run",
        help="run the scheduled pipeline and print a concise summary plus full JSON result",
    )
    scheduled.add_argument("--output-dir", type=Path, default=DEFAULT_CLI_OUTPUT_DIR)
    scheduled.add_argument("--config", type=Path, default=None)
    scheduled.add_argument("--trading-date", required=True)
    scheduled.add_argument("--run-type", choices=("pre_open", "post_close"), required=True)
    scheduled.add_argument("--attempted-at", default=None)
    scheduled.add_argument(
        "--macro-source",
        choices=("live", "manual"),
        default="live",
        help="select the macro-state source for this run",
    )
    scheduled.add_argument(
        "--channel-state",
        action="append",
        default=[],
        metavar="CHANNEL=VALUE",
        help="manual channel override, repeatable (e.g. G=1)",
    )

    backtest = subparsers.add_parser(
        "backtest-run",
        help="run the PIT-safe backtest pipeline and print a concise summary plus full JSON",
    )
    backtest.add_argument("--output-dir", type=Path, default=DEFAULT_CLI_OUTPUT_DIR)
    backtest.add_argument("--config", type=Path, default=None)
    backtest.add_argument("--start-date", required=True)
    backtest.add_argument("--end-date", required=True)
    backtest.add_argument(
        "--run-type",
        default=DEFAULT_BACKTEST_RUN_TYPE,
        choices=("pre_open", "post_close"),
    )

    backtest_stub = subparsers.add_parser(
        "backtest-stub",
        help="run the deterministic backtest wrapper and print a concise summary plus full JSON",
    )
    backtest_stub.add_argument("--output-dir", type=Path, default=DEFAULT_CLI_OUTPUT_DIR)
    backtest_stub.add_argument("--config", type=Path, default=None)
    backtest_stub.add_argument("--start-date", required=True)
    backtest_stub.add_argument("--end-date", required=True)
    backtest_stub.add_argument(
        "--run-type",
        default=DEFAULT_BACKTEST_RUN_TYPE,
        choices=("pre_open", "post_close"),
    )
    return parser


def main() -> int:
    """CLI 진입점을 실행한다."""
    parser = build_parser()
    args = parser.parse_args()
    handler = COMMAND_HANDLERS.get(args.command)
    if handler is not None:
        _print_json(_format_command_output(args.command, handler(args)))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
