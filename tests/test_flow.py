"""Golden path: campaign, replies, opt-out enforcement, handoff."""

from tests.conftest import requires_db, run_db_test


@requires_db
def test_campaign_and_conversation_flow():
    async def scenario():
        from app.conversation import handle_inbound
        from app.db import get_pool
        from app.sender import drain_queue
        from app.store import campaign_stats, create_campaign, queue_message, upsert_contact

        campaign_id = await create_campaign("Test drop", "Hi {first_name}")
        for phone, name in (("+61400000101", "Ana"), ("+61400000102", "Ben")):
            contact = await upsert_contact(phone, name)
            await queue_message(contact["id"], f"Hi {name}", campaign_id=campaign_id)

        counts = await drain_queue()
        assert counts["sent"] == 2

        # Interested reply goes to handoff and queues a response
        result = await handle_inbound("+61400000101", "Yes interested, how much?")
        assert result["action"] == "handoff"

        counts = await drain_queue()
        assert counts["sent"] == 1

        stats = await campaign_stats(campaign_id)
        assert stats["outbound"].get("sent") == 2
        assert stats["handoffs"] == 1

        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT state, intent FROM conversations WHERE state = 'handoff'"
            )
            row = await cur.fetchone()
            assert row == ("handoff", "interested")

    run_db_test(scenario)


@requires_db
def test_opt_out_is_enforced_at_send_time():
    async def scenario():
        from app.conversation import handle_inbound
        from app.db import get_pool
        from app.sender import drain_queue
        from app.store import queue_message, upsert_contact

        contact = await upsert_contact("+61400000201", "Cleo")
        await queue_message(contact["id"], "First touch")
        counts = await drain_queue()
        assert counts["sent"] == 1

        result = await handle_inbound("+61400000201", "STOP")
        assert result["action"] == "opt_out"

        # The confirmation was sent directly, exactly once
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM messages WHERE direction = 'outbound' "
                "AND status = 'sent' AND body LIKE '%unsubscribed%'"
            )
            assert (await cur.fetchone())[0] == 1

        # Anything queued afterwards is suppressed, never sent
        await queue_message(contact["id"], "You should never get this")
        counts = await drain_queue()
        assert counts["sent"] == 0
        assert counts["suppressed"] == 1

        # START opts back in
        result = await handle_inbound("+61400000201", "START")
        assert result["action"] == "opt_in"
        await queue_message(contact["id"], "Welcome back")
        counts = await drain_queue()
        assert counts["sent"] == 1

    run_db_test(scenario)


@requires_db
def test_help_answered_even_when_opted_out():
    async def scenario():
        from app.conversation import handle_inbound
        from app.db import get_pool

        await handle_inbound("+61400000301", "STOP")
        result = await handle_inbound("+61400000301", "HELP")
        assert result["action"] == "help"

        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM messages WHERE direction = 'outbound' AND status = 'sent'"
            )
            # opt-out confirmation plus the help text
            assert (await cur.fetchone())[0] == 2

    run_db_test(scenario)
