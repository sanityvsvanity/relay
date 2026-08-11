"""Deterministic intent classification."""

from app.classify import classify_by_rules


def test_interested():
    assert classify_by_rules("Yes keen, how much?") == "interested"
    assert classify_by_rules("Sounds good, call me") == "interested"


def test_not_interested_wins_over_interested_keywords():
    assert classify_by_rules("No thanks, not interested") == "not_interested"
    assert classify_by_rules("already have one thanks") == "not_interested"


def test_question():
    assert classify_by_rules("Who is this?") == "question"
    assert classify_by_rules("How did you get my number") == "question"


def test_other():
    assert classify_by_rules("ok") == "other"
