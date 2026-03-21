from __future__ import annotations

from datetime import date

from macro_screener.backtest.calendar import is_trading_day, previous_trading_day

SCHEDULED_RUN_TIMES = {"pre_open": "08:30:00+09:00", "post_close": "15:45:00+09:00"}


def build_scheduled_context(trading_date: str, run_type: str) -> dict[str, str]:
    if run_type not in SCHEDULED_RUN_TIMES:
        raise ValueError(f"unsupported run type: {run_type}")
    trade_day = date.fromisoformat(trading_date)
    if not is_trading_day(trade_day):
        raise ValueError(f"scheduled runs require a trading day: {trading_date}")
    as_of_timestamp = f"{trading_date}T{SCHEDULED_RUN_TIMES[run_type]}"
    if run_type == "pre_open":
        input_cutoff = f"{previous_trading_day(trade_day).isoformat()}T18:00:00+09:00"
    else:
        input_cutoff = as_of_timestamp
    return {
        "run_id": f"{trading_date}-{run_type}",
        "run_type": run_type,
        "trading_date": trading_date,
        "as_of_timestamp": as_of_timestamp,
        "input_cutoff": input_cutoff,
        "published_at": as_of_timestamp,
    }
