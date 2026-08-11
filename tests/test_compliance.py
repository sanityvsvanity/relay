"""Compliance keywords and quiet hours."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.compliance import (
    in_quiet_hours,
    is_help,
    is_opt_in,
    is_opt_out,
    next_send_window,
)

MEL = ZoneInfo("Australia/Melbourne")


def test_opt_out_keywords():
    for word in ("STOP", "stop", " Stop ", "UNSUBSCRIBE", "cancel", "END", "quit"):
        assert is_opt_out(word), word


def test_opt_out_requires_exact_keyword():
    # A sentence containing the word is a conversation, not an opt-out
    assert not is_opt_out("please don't stop sending these")
    assert not is_opt_out("what time do deliveries stop?")


def test_opt_in_and_help():
    assert is_opt_in("START")
    assert is_opt_in("yes")
    assert is_help("HELP")
    assert is_help("info")


def test_quiet_hours_overnight_window():
    assert in_quiet_hours(datetime(2026, 7, 20, 23, 0, tzinfo=MEL))
    assert in_quiet_hours(datetime(2026, 7, 21, 6, 30, tzinfo=MEL))
    assert not in_quiet_hours(datetime(2026, 7, 21, 12, 0, tzinfo=MEL))
    assert not in_quiet_hours(datetime(2026, 7, 21, 20, 59, tzinfo=MEL))


def test_next_send_window_defers_to_morning():
    late = datetime(2026, 7, 20, 23, 0, tzinfo=MEL)
    window = next_send_window(late)
    assert window.hour == 9
    assert window.day == 21

    daytime = datetime(2026, 7, 21, 14, 0, tzinfo=MEL)
    assert next_send_window(daytime) == daytime
