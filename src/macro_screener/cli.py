from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
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


def _parse_channel_overrides(values: list[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid channel override: {item}")
        key, raw_value = item.split("=", 1)
        overrides[key.strip()] = int(raw_value.strip())
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Macro screener MVP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_config = subparsers.add_parser(
        "show-config", help="load effective config and print it as JSON"
    )
    show_config.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional path to a YAML config file",
    )

    manual = subparsers.add_parser("manual-run", help="run the non-demo manual MVP pipeline")
    manual.add_argument("--output-dir", required=True)
    manual.add_argument("--config", type=Path, default=None)
    manual.add_argument("--run-id", default=None)
    manual.add_argument("--run-type", default=DEFAULT_DEMO_RUN_TYPE)
    manual.add_argument("--as-of", default=None)
    manual.add_argument("--input-cutoff", default=None)
    manual.add_argument("--published-at", default=None)
    manual.add_argument(
        "--channel-state",
        action="append",
        default=[],
        metavar="CHANNEL=VALUE",
        help="manual channel override, repeatable (e.g. G=1)",
    )

    demo = subparsers.add_parser(
        "demo-run",
        help="deprecated demo wrapper for deterministic local verification",
    )
    demo.add_argument("--output-dir", required=True)
    demo.add_argument("--run-id", default=DEFAULT_DEMO_RUN_ID)
    demo.add_argument("--run-type", default=DEFAULT_DEMO_RUN_TYPE)
    demo.add_argument("--as-of", default=DEFAULT_DEMO_AS_OF)
    demo.add_argument("--input-cutoff", default=DEFAULT_DEMO_INPUT_CUTOFF)
    demo.add_argument("--published-at", default=DEFAULT_DEMO_AS_OF)

    scheduled = subparsers.add_parser("scheduled-run", help="run the scheduled MVP pipeline")
    scheduled.add_argument("--output-dir", required=True)
    scheduled.add_argument("--config", type=Path, default=None)
    scheduled.add_argument("--trading-date", required=True)
    scheduled.add_argument("--run-type", choices=("pre_open", "post_close"), required=True)
    scheduled.add_argument("--attempted-at", default=None)

    backtest = subparsers.add_parser("backtest-run", help="run the PIT-safe MVP backtest pipeline")
    backtest.add_argument("--output-dir", required=True)
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
        help="deprecated wrapper for the backtest pipeline",
    )
    backtest_stub.add_argument("--output-dir", required=True)
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
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "show-config":
        config = load_config(args.config)
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "manual-run":
        channel_states = (
            _parse_channel_overrides(args.channel_state) if args.channel_state else None
        )
        result = run_manual(
            output_dir=args.output_dir,
            config_path=args.config,
            run_id=args.run_id,
            run_type=args.run_type,
            as_of_timestamp=args.as_of,
            input_cutoff=args.input_cutoff,
            published_at=args.published_at,
            channel_states=channel_states,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "demo-run":
        result = run_demo(
            output_dir=args.output_dir,
            run_id=args.run_id,
            run_type=args.run_type,
            as_of_timestamp=args.as_of,
            input_cutoff=args.input_cutoff,
            published_at=args.published_at,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "scheduled-run":
        result = run_scheduled(
            args.output_dir,
            trading_date=args.trading_date,
            run_type=args.run_type,
            attempted_at=args.attempted_at,
            config_path=args.config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "backtest-run":
        result = run_backtest(
            args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
            run_type=args.run_type,
            config_path=args.config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "backtest-stub":
        result = run_backtest_stub(
            args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
            run_type=args.run_type,
            config_path=args.config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
