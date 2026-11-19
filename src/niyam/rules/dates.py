"""Calendar arithmetic used by the rules: month addition and US federal business days."""

import calendar
from datetime import date, timedelta

_SATURDAY, _SUNDAY = 5, 6


def add_months(start: date, months: int) -> date:
    """Same day of the month, `months` later; clamped to the last day of a shorter month."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def federal_holidays(year: int) -> set[date]:
    """Legal public holidays (5 U.S.C. 6103(a)), moved to the observed weekday."""
    fixed = [date(year, 1, 1), date(year, 6, 19), date(year, 7, 4), date(year, 11, 11)]
    fixed.append(date(year, 12, 25))
    floating = [
        _nth_weekday(year, 1, calendar.MONDAY, 3),  # Birthday of Martin Luther King, Jr.
        _nth_weekday(year, 2, calendar.MONDAY, 3),  # Washington's Birthday
        _last_weekday(year, 5, calendar.MONDAY),  # Memorial Day
        _nth_weekday(year, 9, calendar.MONDAY, 1),  # Labor Day
        _nth_weekday(year, 10, calendar.MONDAY, 2),  # Columbus Day
        _nth_weekday(year, 11, calendar.THURSDAY, 4),  # Thanksgiving Day
    ]
    return {_observed(day) for day in fixed} | set(floating)


def is_business_day(day: date) -> bool:
    # NOTE: When Jan 1 falls on a Saturday, its observed holiday is Dec 31 of the prior year,
    # which `federal_holidays` returns under `year + 1`.
    holidays = federal_holidays(day.year)
    if day.month == 12:
        holidays |= federal_holidays(day.year + 1)
    return day.weekday() < _SATURDAY and day not in holidays


def add_business_days(start: date, days: int) -> date:
    """The date `days` business days after `start` (start itself is not counted)."""
    current, remaining = start, days
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current


def _observed(day: date) -> date:
    if day.weekday() == _SATURDAY:
        return day - timedelta(days=1)
    if day.weekday() == _SUNDAY:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)
