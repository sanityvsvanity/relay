"""Data access: contacts, campaigns, conversations, messages."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import get_pool


async def upsert_contact(phone: str, first_name: str = "", attributes: dict | None = None) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO contacts (phone, first_name, attributes) VALUES (%s, %s, %s) "
            "ON CONFLICT (phone) DO UPDATE SET "
            "first_name = CASE WHEN EXCLUDED.first_name <> '' THEN EXCLUDED.first_name ELSE contacts.first_name END "
            "RETURNING id, phone, first_name, opted_out",
            (phone, first_name, json.dumps(attributes or {})),
        )
        row = await cur.fetchone()
        return {"id": row[0], "phone": row[1], "first_name": row[2], "opted_out": row[3]}


async def set_opt_out(contact_id: int, opted_out: bool) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE contacts SET opted_out = %s, opted_out_at = CASE WHEN %s THEN NOW() ELSE NULL END "
            "WHERE id = %s",
            (opted_out, opted_out, contact_id),
        )


async def create_campaign(name: str, template: str) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO campaigns (name, template, status) VALUES (%s, %s, 'sending') RETURNING id",
            (name, template),
        )
        return (await cur.fetchone())[0]


async def last_campaign_for_contact(contact_id: int) -> int | None:
    """The campaign behind the contact's most recent outbound touch.

    Inbound replies attribute to this campaign, which is what makes
    reply and handoff stats per campaign possible.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT campaign_id FROM messages WHERE contact_id = %s "
            "AND direction = 'outbound' AND campaign_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (contact_id,),
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def get_or_create_conversation(contact_id: int, campaign_id: int | None = None) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM conversations WHERE contact_id = %s AND state = 'open' "
            "ORDER BY created_at DESC LIMIT 1",
            (contact_id,),
        )
        row = await cur.fetchone()
        if row:
            if campaign_id is not None:
                await conn.execute(
                    "UPDATE conversations SET campaign_id = COALESCE(campaign_id, %s) WHERE id = %s",
                    (campaign_id, row[0]),
                )
            return row[0]
        cur = await conn.execute(
            "INSERT INTO conversations (contact_id, campaign_id) VALUES (%s, %s) RETURNING id",
            (contact_id, campaign_id),
        )
        return (await cur.fetchone())[0]


async def set_conversation_state(conversation_id: int, state: str, intent: str | None = None) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conversations SET state = %s, intent = COALESCE(%s, intent), "
            "handoff_at = CASE WHEN %s = 'handoff' THEN NOW() ELSE handoff_at END, "
            "updated_at = NOW() WHERE id = %s",
            (state, intent, state, conversation_id),
        )


async def queue_message(
    contact_id: int,
    body: str,
    direction: str = "outbound",
    conversation_id: int | None = None,
    campaign_id: int | None = None,
    queued_for: datetime | None = None,
    status: str = "queued",
) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO messages (contact_id, body, direction, conversation_id, campaign_id, queued_for, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (contact_id, body, direction, conversation_id, campaign_id, queued_for, status),
        )
        return (await cur.fetchone())[0]


async def record_inbound(contact_id: int, conversation_id: int, body: str, provider_sid: str | None) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO messages (contact_id, conversation_id, body, direction, status, provider_sid) "
            "VALUES (%s, %s, %s, 'inbound', 'received', %s) RETURNING id",
            (contact_id, conversation_id, body, provider_sid),
        )
        return (await cur.fetchone())[0]


async def update_delivery_status(provider_sid: str, status: str) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE messages SET status = %s WHERE provider_sid = %s",
            (status, provider_sid),
        )


async def campaign_stats(campaign_id: int) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT status, COUNT(*) FROM messages WHERE campaign_id = %s AND direction = 'outbound' GROUP BY status",
            (campaign_id,),
        )
        outbound = dict(await cur.fetchall())
        cur = await conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN conversations c ON m.conversation_id = c.id "
            "WHERE c.campaign_id = %s AND m.direction = 'inbound'",
            (campaign_id,),
        )
        replies = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE campaign_id = %s AND state = 'handoff'",
            (campaign_id,),
        )
        handoffs = (await cur.fetchone())[0]
    return {"outbound": outbound, "replies": replies, "handoffs": handoffs}
