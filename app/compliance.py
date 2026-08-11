"""Carrier compliance: opt-out and help keywords, quiet hours.

Opt-out handling is not optional in SMS. STOP and friends must always work,
must be confirmed exactly once, and an opted-out contact must never receive
another message from a campaign.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings

OPT_OUT_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "opt out"}
OPT_IN_KEYWORDS = {"start", "unstop", "yes"}
HELP_KEYWORDS = {"help", "info"}

OPT_OUT_CONFIRMATION = (
    "You have been unsubscribed and will not receive further messages. "
    "Reply START to opt back in."
)
HELP_TEXT = "Reply STOP to unsubscribe. Msg and data rates may apply."


def is_opt_out(body: str) -> bool:
    return body.strip().lower() in OPT_OUT_KEYWORDS


def is_opt_in(body: str) -> bool:
    return body.strip().lower() in OPT_IN_KEYWORDS


def is_help(body: str) -> bool:
    return body.strip().lower() in HELP_KEYWORDS


def in_quiet_hours(now: datetime | None = None) -> bool:
    """Campaign sends pause overnight. Conversational replies are exempt:
    someone who texts at 11pm expects an answer at 11pm."""
    tz = ZoneInfo(settings.TIMEZONE)
    local = (now or datetime.now(tz)).astimezone(tz)
    start = time(settings.QUIET_HOURS_START, 0)
    end = time(settings.QUIET_HOURS_END, 0)
    if start <= end:
        return start <= local.time() < end
    return local.time() >= start or local.time() < end


def next_send_window(now: datetime | None = None) -> datetime:
    """The next moment outside quiet hours."""
    tz = ZoneInfo(settings.TIMEZONE)
    local = (now or datetime.now(tz)).astimezone(tz)
    if not in_quiet_hours(local):
        return local
    end = time(settings.QUIET_HOURS_END, 0)
    candidate = local.replace(hour=end.hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate
