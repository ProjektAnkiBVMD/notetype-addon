"""Calendar logic of the Lernplan-Manager: which days are Lernplan days and when each Lerntag falls.

No `anki`/`aqt` imports, so it is easy to test.
Based on "Ankizin-Lernplan Plus" by Lukas Schaffner.
"""
import datetime


DEFAULT_WOCHENTAGE = [True] * 5 + [False] * 2

# first exam day of the M2 dates a Lernplan can be planned towards
M2_TERMINE = {
    "M2 F27 (13.–15. April 2027)": datetime.date(2027, 4, 13),
    "M2 H27 (12.–14. Oktober 2027)": datetime.date(2027, 10, 12),
}


def parse_date(value) -> datetime.date | None:
    """ISO date string (as stored in the config) as a date; None if missing or invalid."""
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_dates(values) -> set[datetime.date]:
    """ISO date strings as a set of dates; invalid entries are dropped."""
    return {day for day in map(parse_date, values or []) if day}


def is_lernplan_day(day: datetime.date, wochentage: list, extra_days=(), skip_days=()) -> bool:
    """Skipped days always win, then extra days, then the active weekdays."""
    if day in skip_days:
        return False
    return day in extra_days or bool(wochentage[day.weekday()])


def remaining_lerntage(order: list[str], current: str, finished: set[str]) -> list[str]:
    """The current Lerntag followed by all unfinished ones after it, in the user's order."""
    start = order.index(current) + 1 if current in order else 0
    return [current] + [n for n in order[start:] if n not in finished and n != current]


def compute_schedule(
    remaining: list[str],
    today: datetime.date,
    wochentage: list,
    extra_days=(),
    skip_days=(),
) -> list[tuple[str, datetime.date]] | None:
    """Assign a date to every remaining Lerntag: the first one is today, the rest follow on the next
    Lernplan days. None if no Lernplan day can ever come (no weekday and no extra day)."""
    extra = set(extra_days) - set(skip_days)
    if not any(wochentage) and not extra:
        return None
    if not remaining:
        return []

    last_extra = max(extra, default=today)
    schedule = [(remaining[0], today)]
    day = today
    for number in remaining[1:]:
        while True:
            day += datetime.timedelta(days=1)
            if is_lernplan_day(day, wochentage, extra, skip_days):
                break
            if not any(wochentage) and day > last_extra:
                return None  # only extra days are left, and they ran out
        schedule.append((number, day))
    return schedule


def finish_date(schedule: list[tuple[str, datetime.date]] | None, today: datetime.date) -> datetime.date | None:
    """Day of the last Lerntag, today if nothing is left, None if the plan can't finish."""
    if schedule is None:
        return None
    return schedule[-1][1] if schedule else today
