"""Date and recurrence math for maintenance tasks."""

from __future__ import annotations

import datetime as _dt
from typing import Iterable


def parse_date(value) -> _dt.date:
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be a string in YYYY-MM-DD format")
    try:
        return _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}: expected YYYY-MM-DD format") from exc


def parse_cost(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("cost must be a non-negative number")
    if isinstance(value, int):
        value = float(value)
    if not isinstance(value, float):
        raise ValueError("cost must be a non-negative number")
    if value < 0 or value in (float("inf"), float("-inf")):
        raise ValueError("cost must be a non-negative number")
    return round(value, 2)


def format_date(d: _dt.date) -> str:
    return d.isoformat()


def add_days(d: _dt.date, days: int) -> _dt.date:
    return d + _dt.timedelta(days=days)


def normalize_season_months(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, Iterable):
        raise ValueError("season_months must be a list of month numbers 1-12")
    months: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError("season_months must be month numbers 1-12")
        try:
            month = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("season_months must be month numbers 1-12") from exc
        if month < 1 or month > 12:
            raise ValueError("season_months must be month numbers 1-12")
        if month not in months:
            months.append(month)
    return sorted(months)


def next_due(last_done: _dt.date, interval_days: int, season_months=None) -> _dt.date:
    """The next date a task is due.

    A plain task is simply ``last_done + interval_days``.  A seasonal task
    (for example, gutter sweeps every spring and fall) additionally slides the
    candidate date forward to the first day of the next month that is within
    the allowed season months.
    """
    if interval_days < 1:
        raise ValueError("interval_days must be at least 1")
    months = normalize_season_months(season_months)
    candidate = add_days(last_done, interval_days)
    if not months:
        return candidate
    year, month = candidate.year, candidate.month
    for _ in range(0, 25):
        if month in months:
            return _dt.date(year, month, 1)
        month += 1
        if month > 12:
            month = 1
            year += 1
    raise RuntimeError("unreachable: no season month matched")


def classify_due(due: _dt.date, as_of: _dt.date, horizon_days: int = 14) -> str:
    if due <= as_of:
        return "overdue"
    if due <= add_days(as_of, horizon_days):
        return "due_soon"
    return "ok"


def warranty_status(until: _dt.date, as_of: _dt.date, horizon_days: int = 14) -> str:
    if until < as_of:
        return "expired"
    if until <= add_days(as_of, horizon_days):
        return "expiring_soon"
    return "active"
