from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from macro_screener.backtest.calendar import is_trading_day, previous_trading_day
from macro_screener.serialization import parse_datetime

SCHEDULED_RUN_TIMES = {"pre_open": "08:30:00+09:00", "post_close": "15:45:00+09:00"}
DEFAULT_TIMEZONE = ZoneInfo("Asia/Seoul")


def scheduled_window_key(trading_date: str, run_type: str) -> str:
    """스케줄 윈도우 키를 만든다."""
    return f"{trading_date}:{run_type}"


def build_scheduled_context(
    trading_date: str,
    run_type: str,
    *,
    attempted_at: str | datetime | None = None,
) -> dict[str, str | dict[str, str]]:
    """스케줄 실행 컨텍스트를 구성한다."""
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

    attempt_dt = (
        parse_datetime(attempted_at)
        if attempted_at is not None
        else datetime.now(DEFAULT_TIMEZONE).replace(microsecond=0)
    )
    run_id = (
        f"{trading_date}-{run_type}-"
        f"{attempt_dt.astimezone(DEFAULT_TIMEZONE).strftime('%Y%m%dT%H%M%S%z')}"
    )
    return {
        "run_id": run_id,
        "run_type": run_type,
        "trading_date": trading_date,
        "as_of_timestamp": as_of_timestamp,
        "input_cutoff": input_cutoff,
        "published_at": attempt_dt.astimezone(DEFAULT_TIMEZONE).isoformat(),
        "scheduled_window_key": {"trading_date": trading_date, "run_type": run_type},
        "scheduled_window_key_text": scheduled_window_key(trading_date, run_type),
    }
