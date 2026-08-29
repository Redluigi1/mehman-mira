from datetime import date

from app.pipeline.dates import resolve_date_expression

TODAY = date(2026, 9, 2)  # Wednesday, matches the seeded demo_today


def test_this_weekend_resolves_to_friday_sunday():
    r = resolve_date_expression("this weekend", TODAY)
    assert r.check_in == date(2026, 9, 4)  # Friday
    assert r.check_out == date(2026, 9, 6)  # Sunday
    assert r.nights == 2


def test_next_weekend_is_one_week_later():
    r = resolve_date_expression("next weekend", TODAY)
    assert r.check_in == date(2026, 9, 11)
    assert r.check_out == date(2026, 9, 13)


def test_tomorrow():
    r = resolve_date_expression("tomorrow", TODAY)
    assert r.check_in == date(2026, 9, 3)
    assert r.nights == 1


def test_in_n_days():
    r = resolve_date_expression("in 5 days", TODAY)
    assert r.check_in == date(2026, 9, 7)


def test_explicit_range_same_month():
    r = resolve_date_expression("Sep 10 to 13", TODAY)
    assert r.check_in == date(2026, 9, 10)
    assert r.check_out == date(2026, 9, 13)
    assert r.nights == 3


def test_nights_combined_with_relative_start():
    r = resolve_date_expression("tomorrow for 4 nights", TODAY)
    assert r.check_in == date(2026, 9, 3)
    assert r.check_out == date(2026, 9, 7)
    assert r.nights == 4


def test_single_date_with_known_nights_from_state():
    r = resolve_date_expression("September 20th", TODAY, known_nights=2)
    assert r.check_in == date(2026, 9, 20)
    assert r.check_out == date(2026, 9, 22)


def test_bare_month_day_in_the_past_is_left_as_is_not_silently_rolled_forward():
    # Guessing "next year" would silently book a date the guest never said —
    # the conflict engine's PAST_DATE check needs the literal past date to
    # flag it and ask, per the "unknown means unknown" invariant.
    r = resolve_date_expression("January 5", TODAY)
    assert r.check_in == date(2026, 1, 5)


def test_ordinal_suffixes_dont_break_range_parsing():
    r = resolve_date_expression("12th july to 14th", TODAY)
    assert r.check_in == date(2026, 7, 12)
    assert r.check_out == date(2026, 7, 14)
    assert r.nights == 2


def test_empty_expression_keeps_known_nights_only():
    r = resolve_date_expression(None, TODAY, known_nights=3)
    assert r.check_in is None
    assert r.nights == 3


def test_unparseable_gibberish_returns_no_dates():
    r = resolve_date_expression("sometime nice", TODAY)
    assert r.check_in is None
