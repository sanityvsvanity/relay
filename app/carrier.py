"""Carrier port: mock for demo mode, Twilio for live."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

import httpx

from app.config import settings


class CarrierPort(Protocol):
    async def send_sms(self, to: str, body: str) -> dict[str, Any]: ...


class MockCarrier:
    """Prints instead of sending. Returns a fake provider sid."""

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        sid = f"MOCK{uuid.uuid4().hex[:10]}"
        print(f"[MOCK sms -> {to}] {body[:120]}")
        return {"sid": sid, "status": "sent"}


class TwilioCarrier:
    """Twilio Messages API via httpx."""

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                data={
                    "To": to,
                    "From": settings.TWILIO_FROM_NUMBER,
                    "Body": body,
                    "StatusCallback": f"{settings.PUBLIC_BASE_URL}/webhooks/status",
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            resp.raise_for_status()
            data = resp.json()
            return {"sid": data["sid"], "status": data["status"]}


_carrier: CarrierPort | None = None


def get_carrier() -> CarrierPort:
    global _carrier
    if _carrier is None:
        if settings.DEMO_MODE or not settings.TWILIO_ACCOUNT_SID:
            _carrier = MockCarrier()
        else:
            _carrier = TwilioCarrier()
    return _carrier


def reset_carrier() -> None:
    global _carrier
    _carrier = None
