"""The conversation loop: what happens when a reply comes in.

Order matters. Compliance keywords are handled before anything else, then
classification, then handoff or reply. Hot leads go to a human with the full
context. The engine drafts and sends conversational replies, but it never
invents pricing or commitments, and an opted-out contact ends the loop
immediately.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.classify import classify
from app.compliance import (
    HELP_TEXT,
    OPT_OUT_CONFIRMATION,
    is_help,
    is_opt_in,
    is_opt_out,
)
from app.config import settings
from app.reply import generate_reply
from app.store import (
    get_or_create_conversation,
    last_campaign_for_contact,
    queue_message,
    record_inbound,
    set_conversation_state,
    set_opt_out,
    upsert_contact,
)


async def handle_inbound(phone: str, body: str, provider_sid: str | None = None) -> dict[str, Any]:
    """Process one inbound SMS end to end. Returns what happened."""
    contact = await upsert_contact(phone)
    campaign_id = await last_campaign_for_contact(contact["id"])
    conversation_id = await get_or_create_conversation(contact["id"], campaign_id)
    await record_inbound(contact["id"], conversation_id, body, provider_sid)

    # Compliance first, always
    if is_opt_out(body):
        await set_opt_out(contact["id"], True)
        await set_conversation_state(conversation_id, "closed", "opt_out")
        # The single confirmation is required and allowed post opt-out, so it
        # sends directly instead of entering the queue, which would suppress it.
        await _send_direct(contact, conversation_id, OPT_OUT_CONFIRMATION)
        return {"action": "opt_out", "conversation_id": conversation_id}

    if is_opt_in(body):
        await set_opt_out(contact["id"], False)
        return {"action": "opt_in", "conversation_id": conversation_id}

    if is_help(body):
        # HELP must be answered even for opted-out contacts, so it also
        # bypasses the queue.
        await _send_direct(contact, conversation_id, HELP_TEXT)
        return {"action": "help", "conversation_id": conversation_id}

    intent = await classify(body)

    if intent == "interested":
        await set_conversation_state(conversation_id, "handoff", intent)
        await _notify_handoff(contact, conversation_id, body)
        reply = await generate_reply(intent, body, contact["first_name"])
        await queue_message(contact["id"], reply, conversation_id=conversation_id)
        return {"action": "handoff", "intent": intent, "conversation_id": conversation_id}

    await set_conversation_state(conversation_id, "open", intent)
    reply = await generate_reply(intent, body, contact["first_name"])
    await queue_message(contact["id"], reply, conversation_id=conversation_id)
    return {"action": "replied", "intent": intent, "conversation_id": conversation_id}


async def _send_direct(contact: dict, conversation_id: int, body: str):
    """Send a compliance message immediately and record it as sent."""
    from app.carrier import get_carrier

    carrier = get_carrier()
    result = await carrier.send_sms(contact["phone"], body)
    msg_id = await queue_message(
        contact["id"], body, conversation_id=conversation_id, status="sent"
    )
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE messages SET provider_sid = %s, sent_at = NOW() WHERE id = %s",
            (result["sid"], msg_id),
        )


async def _notify_handoff(contact: dict, conversation_id: int, body: str):
    """Tell a human. Webhook when configured, log line otherwise."""
    payload = {
        "conversation_id": conversation_id,
        "phone": contact["phone"],
        "first_name": contact["first_name"],
        "last_message": body,
        "reason": "interested",
    }
    if settings.HANDOFF_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.HANDOFF_WEBHOOK_URL, json=payload)
        except Exception as exc:
            print(f"[handoff] webhook failed, falling back to log: {exc}")
            print(f"[handoff] HOT LEAD {payload}")
    else:
        print(f"[handoff] HOT LEAD {payload}")
