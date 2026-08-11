"""Reply intent classification.

Deterministic keyword pass by default so the whole engine runs with zero
credentials. With an Anthropic key set the classifier upgrades to an LLM,
with the keyword pass kept as the fallback on any error.
"""

from __future__ import annotations

from app.config import settings

INTENTS = ("interested", "question", "not_interested", "other")

_INTERESTED = ("yes", "interested", "keen", "tell me more", "sounds good", "how much", "price", "book", "call me")
_NOT_INTERESTED = ("no thanks", "not interested", "no thank", "already have", "not for me")
_QUESTION_MARKERS = ("?", "who is this", "what is this", "how did you get")


def classify_by_rules(body: str) -> str:
    text = body.strip().lower()
    if any(k in text for k in _NOT_INTERESTED):
        return "not_interested"
    if any(k in text for k in _INTERESTED):
        return "interested"
    if any(k in text for k in _QUESTION_MARKERS):
        return "question"
    return "other"


async def classify(body: str) -> str:
    if settings.DEMO_MODE or not settings.ANTHROPIC_API_KEY:
        return classify_by_rules(body)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.MODEL_REPLY,
            max_tokens=10,
            system=(
                "Classify the SMS reply into exactly one word from: "
                "interested, question, not_interested, other."
            ),
            messages=[{"role": "user", "content": body}],
        )
        intent = msg.content[0].text.strip().lower()
        return intent if intent in INTENTS else classify_by_rules(body)
    except Exception:
        return classify_by_rules(body)
