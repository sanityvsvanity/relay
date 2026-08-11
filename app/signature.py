"""Twilio webhook signature verification.

X-Twilio-Signature is base64(HMAC-SHA1(auth_token, url + sorted form params)).
Rule: missing auth token rejects when ENV=prod, warns and passes in dev.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.config import settings


def verify_twilio_signature(url: str, params: dict[str, str], signature: str) -> bool:
    if not settings.TWILIO_AUTH_TOKEN:
        if settings.ENV == "prod":
            return False
        print("[signature] Warning: no Twilio auth token, passing in dev mode")
        return True

    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(
            settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature)
