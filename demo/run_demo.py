"""Headless demo: a campaign send and four conversations, zero credentials.

Everything executes for real against Postgres: the outbound queue with its
opt-out, quiet hours and rate limit checks, the inbound conversation loop,
compliance keywords, intent classification and the hot lead handoff. The
carrier is mocked, so no SMS leaves the machine and no Twilio account is
needed. Replies are template-based in demo mode; an Anthropic key upgrades
them to an LLM.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.conversation import handle_inbound
from app.db import close_pool, get_pool
from app.sender import drain_queue
from app.store import campaign_stats, create_campaign, queue_message, upsert_contact

DATA_DIR = Path(__file__).parent / "data"
WIDTH = 60

TEMPLATE = (
    "Hi {first_name}, our new season range is out now, starting at $520. "
    "Want the details? Reply YES for the catalogue or STOP to opt out."
)


def banner(text: str):
    print("\n" + "=" * WIDTH)
    print(f"  {text}")
    print("=" * WIDTH)


def step(n: int, total: int, title: str):
    print(f"\n[{n}/{total}] {title}")
    print("-" * WIDTH)


async def reset_state():
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE messages, conversations, campaigns, contacts RESTART IDENTITY CASCADE"
        )
    print("State cleared.")


async def run_demo(reset: bool = False):
    banner("Relay demo: conversational SMS at campaign scale")

    if reset:
        await reset_state()

    contacts = json.loads((DATA_DIR / "contacts.json").read_text())

    step(1, 5, "Queue a campaign to six contacts")
    campaign_id = await create_campaign("New season release", TEMPLATE)
    for entry in contacts:
        contact = await upsert_contact(entry["phone"], entry["first_name"], entry["attributes"])
        body = TEMPLATE.format(first_name=contact["first_name"])
        await queue_message(contact["id"], body, campaign_id=campaign_id)
    print(f"  campaign {campaign_id} created, 6 messages queued")

    step(2, 5, "Drain the queue through the rate limiter")
    counts = await drain_queue()
    print(f"  {counts}")

    step(3, 5, "Replies come in: interested, question, opt out")
    r1 = await handle_inbound("+61400000001", "Yes keen, how much are the larger sizes?")
    print(f"  Priya: {r1['action']} (intent: {r1.get('intent')})")
    r2 = await handle_inbound("+61400000002", "Who is this? How did you get my number?")
    print(f"  Tom: {r2['action']} (intent: {r2.get('intent')})")
    r3 = await handle_inbound("+61400000003", "STOP")
    print(f"  Mei: {r3['action']}")

    step(4, 5, "Queued replies go out, opt-out is enforced")
    counts = await drain_queue()
    print(f"  {counts}")
    # A second campaign touch proves the opt-out sticks
    contact = await upsert_contact("+61400000003")
    await queue_message(contact["id"], "Follow-up you should never receive", campaign_id=campaign_id)
    counts = await drain_queue()
    print(f"  follow-up to opted-out contact: {counts}")

    step(5, 5, "Stats readback from Postgres")
    stats = await campaign_stats(campaign_id)
    print(f"  outbound: {stats['outbound']}")
    print(f"  replies: {stats['replies']}, handoffs: {stats['handoffs']}")

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT c.phone, c.opted_out FROM contacts c ORDER BY c.id"
        )
        rows = await cur.fetchall()

    banner("Demo complete")
    print("\nContacts:")
    for phone, opted_out in rows:
        print(f"  {phone}  {'OPTED OUT' if opted_out else 'active'}")
    print("\nZero credentials required. Inspect with:")
    print("  docker exec -it relay-postgres-1 psql -U relay -d relay")
    await close_pool()


def main():
    parser = argparse.ArgumentParser(description="Run the Relay demo")
    parser.add_argument("--reset", action="store_true", help="Clear state before running")
    args = parser.parse_args()
    asyncio.run(run_demo(reset=args.reset))


if __name__ == "__main__":
    main()
