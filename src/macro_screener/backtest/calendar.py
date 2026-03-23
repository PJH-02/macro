from __future__ import annotations

from datetime import date, timedelta

MVP_HOLIDAYS = frozenset({"2026-01-01"})


def is_trading_day(day: date) -> bool:
    """거래일 여부를 판단한다."""
    return day.weekday() < 5 and day.isoformat() not in MVP_HOLIDAYS


def previous_trading_day(day: date) -> date:
    """이전 거래일을 계산한다."""
    previous = day - timedelta(days=1)
    while not is_trading_day(previous):
        previous -= timedelta(days=1)
    return previous


def iter_trading_dates(start_date: str, end_date: str) -> list[str]:
    """구간 내 거래일 목록을 생성한다."""
    current = date.fromisoformat(start_date)
    final = date.fromisoformat(end_date)
    if current > final:
        raise ValueError("start_date must be on or before end_date")
    dates: list[str] = []
    while current <= final:
        if is_trading_day(current):
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates
