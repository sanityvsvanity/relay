"""Relay: a conversational SMS engine for outbound marketing at scale."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.config import settings
from app.conversation import handle_inbound
from app.sender import drain_queue
from app.signature import verify_twilio_signature
from app.store import campaign_stats, create_campaign, queue_message, upsert_contact

load_dotenv()

SENDER_INTERVAL_SECONDS = 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_sender_loop())
    yield
    task.cancel()


async def _sender_loop():
    while True:
        try:
            await drain_queue()
        except Exception as exc:
            print(f"[sender] loop error: {exc}")
        await asyncio.sleep(SENDER_INTERVAL_SECONDS)


app = FastAPI(title="Relay", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


class CampaignIn(BaseModel):
    name: str
    template: str
    contacts: list[dict]


@app.post("/api/campaigns")
async def start_campaign(campaign: CampaignIn):
    """Create a campaign and queue the first touch to every contact.

    The queue enforces opt-out, quiet hours and the rate limit; this endpoint
    just gets the rows in.
    """
    campaign_id = await create_campaign(campaign.name, campaign.template)
    queued = 0
    for entry in campaign.contacts:
        contact = await upsert_contact(
            entry["phone"], entry.get("first_name", ""), entry.get("attributes")
        )
        if contact["opted_out"]:
            continue
        body = campaign.template.format(first_name=contact["first_name"] or "there")
        await queue_message(contact["id"], body, campaign_id=campaign_id)
        queued += 1
    return {"campaign_id": campaign_id, "queued": queued}


@app.get("/api/campaigns/{campaign_id}/stats")
async def get_stats(campaign_id: int):
    return await campaign_stats(campaign_id)


@app.post("/webhooks/sms")
async def inbound_sms(request: Request, From: str = Form(...), Body: str = Form(...), MessageSid: str = Form(default="")):
    """Twilio inbound message webhook."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("x-twilio-signature", "")
    url = f"{settings.PUBLIC_BASE_URL}/webhooks/sms"
    if not verify_twilio_signature(url, form, signature):
        return JSONResponse({"error": "invalid_signature"}, status_code=401)

    asyncio.create_task(handle_inbound(From, Body, MessageSid))
    # Empty TwiML: replies go out through the queue, not the webhook response
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@app.post("/webhooks/status")
async def delivery_status(request: Request, MessageSid: str = Form(...), MessageStatus: str = Form(...)):
    """Twilio delivery receipt webhook."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("x-twilio-signature", "")
    url = f"{settings.PUBLIC_BASE_URL}/webhooks/status"
    if not verify_twilio_signature(url, form, signature):
        return JSONResponse({"error": "invalid_signature"}, status_code=401)

    from app.store import update_delivery_status

    await update_delivery_status(MessageSid, MessageStatus)
    return {"ok": True}
