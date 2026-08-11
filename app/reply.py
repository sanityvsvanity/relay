"""Reply generation: templates in demo mode, LLM when a key is configured.

Either way the reply is bounded: one SMS, no promises, no pricing invented.
"""

from __future__ import annotations

from app.config import settings

TEMPLATES = {
    "interested": (
        "Great to hear {first_name}. One of the team will text you shortly to "
        "sort out the details. Anything specific you want covered?"
    ),
    "question": (
        "Good question {first_name}. A team member will come back to you with "
        "the details today. Anything else you want to know?"
    ),
    "not_interested": "No worries {first_name}, thanks for letting us know. Reply STOP to unsubscribe.",
    "other": "Thanks for the reply {first_name}. Could you tell me a bit more so I can point you the right way?",
}

SYSTEM_PROMPT = (
    "You write one short SMS reply for an Australian business. Rules: under "
    "300 characters, plain language, no emojis, never invent pricing or "
    "commitments, never claim to be human, and if the person seems keen say "
    "a team member will follow up shortly."
)


async def generate_reply(intent: str, body: str, first_name: str = "") -> str:
    name = first_name or "there"
    if settings.DEMO_MODE or not settings.ANTHROPIC_API_KEY:
        return TEMPLATES.get(intent, TEMPLATES["other"]).format(first_name=name)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.MODEL_REPLY,
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Their name: {name}\nTheir intent: {intent}\nTheir message: {body}",
                }
            ],
        )
        return msg.content[0].text.strip()[:320]
    except Exception:
        return TEMPLATES.get(intent, TEMPLATES["other"]).format(first_name=name)
