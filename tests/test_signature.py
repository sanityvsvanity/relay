"""Twilio signature verification rules."""

import base64
import hashlib
import hmac

from app.config import settings
from app.signature import verify_twilio_signature

URL = "https://relay.example.com/webhooks/sms"
PARAMS = {"From": "+61400000001", "Body": "Yes keen", "MessageSid": "SM123"}
TOKEN = "test-auth-token"


def _sign(url: str, params: dict, token: str) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


def test_valid_signature(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    assert verify_twilio_signature(URL, PARAMS, _sign(URL, PARAMS, TOKEN))


def test_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    assert not verify_twilio_signature(URL, PARAMS, _sign(URL, PARAMS, "other-token"))


def test_tampered_params(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    sig = _sign(URL, PARAMS, TOKEN)
    tampered = {**PARAMS, "Body": "changed"}
    assert not verify_twilio_signature(URL, tampered, sig)


def test_missing_token_rejects_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "ENV", "prod")
    assert not verify_twilio_signature(URL, PARAMS, "anything")


def test_missing_token_passes_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "ENV", "dev")
    assert verify_twilio_signature(URL, PARAMS, "anything")
