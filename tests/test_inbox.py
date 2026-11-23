"""Real PostgreSQL transaction/lease tests; isolated database required."""

import asyncio
import json
import os
import time
from dataclasses import replace

import httpx
import pytest
from psycopg.conninfo import conninfo_to_dict
from pywa_async import WhatsApp
from test_main import SETTINGS, envelope, signed_headers

from univio.app import create_app
from univio.config import DatabaseConfig
from univio.delivery import ReplyService
from univio.events import Event
from univio.inbox import Inbox
from univio.migrate import migrate
from univio.runtime import run_async
from univio.worker import process_one


@pytest.mark.postgres
def test_postgres_acceptance_recovery_and_retention():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated database ending in _test")
    if not conninfo_to_dict(url).get("dbname", "").endswith("_test"):
        pytest.fail("Integration tests require a database name ending in _test")

    async def scenario():
        config = DatabaseConfig(url)
        await migrate(config)
        await migrate(config)  # Re-applying is harmless.
        first, second = Inbox(config), Inbox(config)
        try:
            await first.open()
            await second.open()
            async with first.pool.connection() as conn:
                await conn.execute("TRUNCATE inbox")
            event = Event(
                "one", "27821234567", int(time.time()), "PRIVATE FREE TEXT", "text"
            )
            await asyncio.gather(
                first.accept([event], "123"), second.accept([event], "123")
            )
            assert await first.counts() == {"pending": 1}
            claims = await asyncio.gather(first.claim("123"), second.claim("123"))
            job = next(item for item in claims if item)
            assert sum(item is not None for item in claims) == 1
            assert job["command"] is None  # Never persist arbitrary user text.
            assert await first.claim("another-phone") is None
            # Crash recovery: an expired lease can be claimed with a new token.
            async with first.pool.connection() as conn:
                await conn.execute(
                    "UPDATE inbox SET lease_until=now()-interval '1 second'"
                )
            recovered = await second.claim("123")
            assert recovered["lease_token"] != job["lease_token"]
            await first.finish(job)  # Stale completion cannot mark the new claim sent.
            assert await first.counts() == {"processing": 1}
            await second.finish(recovered, error="transport")
            assert await first.counts() == {"pending": 1}
            async with first.pool.connection() as conn:
                await conn.execute("UPDATE inbox SET available_at=now()")
            retry = await first.claim("123")
            await first.finish(retry)
            await first.accept([event], "123")
            assert await first.counts() == {"sent": 1}
            async with first.pool.connection() as conn:
                row = await (
                    await conn.execute("SELECT recipient FROM inbox")
                ).fetchone()
                assert row["recipient"] is None
                await conn.execute(
                    "UPDATE inbox SET updated_at=now()-interval '9 days'"
                )
            await first.maintain()
            assert await first.counts() == {}
            old = Event("old", "27821234567", int(time.time()) - 90000, "menu", "text")
            await first.accept([old], "123")
            await first.maintain()
            assert await first.counts() == {"dead": 1}
            # Exercise the HTTP acceptance-to-worker path against real PostgreSQL.
            async with first.pool.connection() as conn:
                await conn.execute("TRUNCATE inbox")
            app = create_app(replace(SETTINGS, database=config), inbox=second)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app), base_url="http://test"
                ) as client:
                    body = json.dumps(envelope()).encode()
                    response = await client.post(
                        "/webhook", content=body, headers=signed_headers(body)
                    )
                    assert response.status_code == 200
                    assert await first.counts() == {"pending": 1}
                    assert (await client.get("/ready")).status_code == 200
                sends = []

                def meta(request):
                    sends.append(request)
                    return httpx.Response(
                        200,
                        json={
                            "messaging_product": "whatsapp",
                            "contacts": [
                                {"input": "27821234567", "wa_id": "27821234567"}
                            ],
                            "messages": [{"id": "out"}],
                        },
                    )

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(meta)
                ) as session:
                    wa = WhatsApp(
                        phone_id=SETTINGS.phone_id,
                        token=SETTINGS.access_token,
                        session=session,
                    )
                    assert await process_one(first, ReplyService(wa), SETTINGS.phone_id)
                    assert await first.counts() == {"sent": 1}
                    assert len(sends) == 1
        finally:
            await first.close()
            await second.close()

    run_async(scenario())
