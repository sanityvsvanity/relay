# Relay

A conversational SMS engine for outbound marketing at scale. Campaigns go out through a rate-limited queue, replies come back into a conversation loop that classifies intent and answers in seconds, hot leads get routed to a human with full context, and every message lands in Postgres.

I built the production version of this pattern for a client. That system is theirs. This repo is a clean-room reference implementation of the architecture: none of the production code, all of the load-bearing decisions.

## Quickstart

```bash
git clone https://github.com/sanityvsvanity/relay && cd relay
docker compose up -d
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m demo.run_demo --reset
```

No credentials. The demo queues a campaign to six contacts, drains it through the rate limiter, feeds back an interested reply, a question and a STOP, then reads the resulting state out of Postgres:

```
outbound: {'sent': 6, 'suppressed': 1}
replies: 3, handoffs: 1

+61400000001  active
+61400000003  OPTED OUT
```

The carrier is mocked in demo mode and replies are template-based. Set Twilio credentials and an Anthropic key and the same code sends real SMS with LLM-drafted replies.

## The decisions that matter at volume

**Compliance is not a feature, it is the floor.** STOP, UNSUBSCRIBE, CANCEL and friends are matched as exact keywords before anything else touches the message. Opt-out is enforced at send time, not just at queue time, so a message queued before the opt-out still gets suppressed. The one legally required confirmation sends directly, bypassing its own suppression rule. HELP is answered even for opted-out contacts. START opts back in.

**Every send goes through one queue.** Campaign blasts and conversational replies use the same outbox, so there is exactly one place where opt-out, quiet hours and rate limiting are enforced. A token bucket keeps a large campaign from bursting past carrier limits.

**Quiet hours defer, replies do not.** Campaign messages queued at 11pm wait for 9am. A person who texts you at 11pm gets their answer at 11pm, because that is how conversations work.

**Hot leads leave the machine.** When intent classification says interested, the conversation flips to handoff, a human gets the full context through a webhook, and the engine tells the prospect a person will follow up. The LLM never negotiates, never invents pricing, never pretends to be human.

**Intent classification degrades gracefully.** Keyword rules by default, LLM when a key is configured, keyword fallback on any LLM error. The engine never stalls on a provider outage.

## Architecture

```
POST /api/campaigns          queue the first touch to a contact list
POST /webhooks/sms           Twilio inbound, signature verified
POST /webhooks/status        delivery receipts
GET  /api/campaigns/{id}/stats

app/sender.py                the outbox: opt-out, quiet hours, token bucket
app/conversation.py          the loop: compliance, classify, handoff or reply
app/compliance.py            STOP/HELP/START, quiet hours windows
app/classify.py              keyword rules, optional LLM upgrade
app/reply.py                 bounded reply generation
app/signature.py             Twilio HMAC-SHA1 verification
```

Inbound webhooks return empty TwiML immediately; replies go out through the queue like everything else. Twilio signatures are verified with a constant-time compare, and a missing auth token rejects in prod, warns in dev.

## Tests

```bash
.venv/bin/python -m pytest
```

19 tests: compliance keywords and quiet hours, signature verification, the token bucket, intent rules, and DB-backed golden paths for the campaign flow, opt-out enforcement and the help-while-opted-out case.

## Who built this

Gagan Dasari. I run [GTMpro](https://gtmpro.com.au), an agentic GTM engineering practice in Melbourne. Relay is one of the systems in the [catalogue](https://gtmpro.com.au).

gagan@gtmpro.com.au · [LinkedIn](https://www.linkedin.com/in/gaganbuilds) · [GitHub](https://github.com/sanityvsvanity)
