"""Deterministic date resolution from a raw `date_expression` phrase against
an explicit `today` anchor (plan §3, stage 1). The extractor proposes the
phrase; this module — not the model — decides what it means.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil import parser as dateutil_parser

FRIDAY = 4  # Monday == 0

_WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


@dataclass
class DateResolution:
    check_in: date | None = None
    check_out: date | None = None
    nights: int | None = None


def _next_weekday_on_or_after(today: date, weekday: int) -> date:
    days_ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


def _explicit_nights(text: str) -> int | None:
    m = re.search(r"(\d+)\s*nights?", text)
    return int(m.group(1)) if m else None


def _relative_night_delta(text: str) -> int | None:
    """"one more night", "2 extra nights", "another night" — a stay-length
    adjustment relative to what's already known, not a fresh duration
    (EC2, plan §12). Only meaningful combined with `known_nights`.
    """
    m = re.search(r"\b(a|an|one|two|three|four|five|\d+)\s+(?:more|extra|additional)\s+nights?\b", text)
    if m:
        token = m.group(1)
        return int(token) if token.isdigit() else _WORD_NUMBERS.get(token)
    if re.search(r"\banother\s+night\b", text):
        return 1
    return None


def _try_parse_range(text: str, today: date) -> tuple[date, date] | None:
    m = re.search(
        r"(?P<a>[a-z0-9]+(?:\s+[a-z]+)?)\s*(?:-|to|through|thru)\s*(?P<b>[a-z0-9]+(?:\s+[a-z]+)?)",
        text,
    )
    if not m:
        return None
    month_hint = re.search(r"[a-z]{3,9}", text)
    a_text, b_text = m.group("a"), m.group("b")
    try:
        if month_hint and not re.search(r"[a-z]", a_text):
            a_text = f"{a_text} {month_hint.group(0)}"
        if month_hint and not re.search(r"[a-z]", b_text):
            b_text = f"{b_text} {month_hint.group(0)}"
        start = dateutil_parser.parse(a_text, default=_default_dt(today), fuzzy=True).date()
        end = dateutil_parser.parse(b_text, default=_default_dt(today), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    if end <= start:
        return None
    start, end = _roll_forward_if_past(start, today), end
    if end < start:
        end = end.replace(year=start.year)
    return start, end


def _default_dt(today: date):
    from datetime import datetime
    return datetime(today.year, today.month, today.day)


def _roll_forward_if_past(d: date, today: date) -> date:
    while d < today:
        d = d.replace(year=d.year + 1)
    return d


def _try_parse_single(text: str, today: date) -> date | None:
    try:
        parsed = dateutil_parser.parse(text, default=_default_dt(today), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    return _roll_forward_if_past(parsed, today)


def resolve_date_expression(expression: str | None, today: date, known_nights: int | None = None) -> DateResolution:
    if not expression or not expression.strip():
        return DateResolution(nights=known_nights)

    text = expression.strip().lower()
    nights = _explicit_nights(text) or known_nights

    night_delta = _relative_night_delta(text)
    if night_delta is not None and known_nights is not None:
        return DateResolution(nights=known_nights + night_delta)

    if "next weekend" in text:
        this_friday = _next_weekday_on_or_after(today, FRIDAY)
        friday = this_friday + timedelta(days=7)
        return DateResolution(check_in=friday, check_out=friday + timedelta(days=nights or 2), nights=nights or 2)

    if "this weekend" in text or text.strip() == "weekend":
        friday = _next_weekday_on_or_after(today, FRIDAY)
        return DateResolution(check_in=friday, check_out=friday + timedelta(days=nights or 2), nights=nights or 2)

    if "tonight" in text or text.strip() == "today":
        return DateResolution(check_in=today, check_out=today + timedelta(days=nights or 1), nights=nights or 1)

    if "tomorrow" in text:
        start = today + timedelta(days=1)
        return DateResolution(check_in=start, check_out=start + timedelta(days=nights or 1), nights=nights or 1)

    m = re.search(r"in (\d+) days?", text)
    if m:
        start = today + timedelta(days=int(m.group(1)))
        return DateResolution(check_in=start, check_out=start + timedelta(days=nights or 1), nights=nights or 1)

    range_result = _try_parse_range(text, today)
    if range_result:
        check_in, check_out = range_result
        return DateResolution(check_in=check_in, check_out=check_out, nights=(check_out - check_in).days)

    single = _try_parse_single(text, today)
    if single:
        if nights:
            return DateResolution(check_in=single, check_out=single + timedelta(days=nights), nights=nights)
        return DateResolution(check_in=single, nights=nights)

    return DateResolution(nights=nights)
