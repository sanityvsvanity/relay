"""Outbound queue worker.

Every send goes through here: campaign blasts and conversational replies
alike. Enforced on the way out, in order:

1. Opt-out check at send time, not just at queue time
2. Quiet hours deferral for campaign messages (replies are exempt)
3. Token bucket rate limit so a big campaign cannot burst past carrier limits
"""

from __future__ import annotations

import asyncio
import time as time_mod
from datetime import datetime, timezone

from app.carrier import get_carrier
from app.compliance import in_quiet_hours, next_send_window
from app.config import settings
from app.db import get_pool


class TokenBucket:
    def __init__(self, rate_per_second: float, capacity: float | None = None):
        self.rate = rate_per_second
        self.capacity = capacity or rate_per_second
        self.tokens = self.capacity
        self.updated = time_mod.monotonic()

    def try_acquire(self) -> bool:
        now = time_mod.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    async def acquire(self):
        while not self.try_acquire():
            await asyncio.sleep(1 / self.rate)


_bucket: TokenBucket | None = None


def get_bucket() -> TokenBucket:
    global _bucket
    if _bucket is None:
        _bucket = TokenBucket(settings.RATE_LIMIT_PER_SECOND)
    return _bucket


async def drain_queue(limit: int = 500) -> dict[str, int]:
    """Send due queued messages. Returns counts by outcome."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    counts = {"sent": 0, "deferred": 0, "suppressed": 0, "failed": 0}

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT m.id, m.body, m.campaign_id, c.phone, c.opted_out "
            "FROM messages m JOIN contacts c ON m.contact_id = c.id "
            "WHERE m.direction = 'outbound' AND m.status = 'queued' "
            "AND (m.queued_for IS NULL OR m.queued_for <= %s) "
            "ORDER BY m.id LIMIT %s",
            (now, limit),
        )
        due = await cur.fetchall()

    carrier = get_carrier()
    bucket = get_bucket()

    for msg_id, body, campaign_id, phone, opted_out in due:
        # Opt-out wins over everything, including messages queued before the opt-out
        if opted_out:
            await _set_status(msg_id, "suppressed")
            counts["suppressed"] += 1
            continue

        # Campaign messages respect quiet hours; conversational replies do not
        if campaign_id is not None and in_quiet_hours():
            await _defer(msg_id, next_send_window())
            counts["deferred"] += 1
            continue

        await bucket.acquire()
        try:
            result = await carrier.send_sms(phone, body)
            await _mark_sent(msg_id, result["sid"])
            counts["sent"] += 1
        except Exception as exc:
            print(f"[sender] send failed for message {msg_id}: {exc}")
            await _set_status(msg_id, "failed")
            counts["failed"] += 1

    return counts


async def _set_status(msg_id: int, status: str):
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute("UPDATE messages SET status = %s WHERE id = %s", (status, msg_id))


async def _defer(msg_id: int, when):
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute("UPDATE messages SET queued_for = %s WHERE id = %s", (when, msg_id))


async def _mark_sent(msg_id: int, sid: str):
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE messages SET status = 'sent', provider_sid = %s, sent_at = NOW() WHERE id = %s",
            (sid, msg_id),
        )
