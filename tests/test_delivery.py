"""Deterministic retry/concurrency tests; no real WhatsApp calls."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from univio.delivery import DeliveryBusy, ReplyService
from univio.events import Event


def event(identifier="one"):
    return Event(identifier, "27821234567", 0, "menu", "text")


def test_concurrent_duplicate_retries_until_original_completes():
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def send(**kwargs):
            started.set()
            await finish.wait()

        wa = AsyncMock()
        wa.send_message.side_effect = send
        service = ReplyService(wa)
        first = asyncio.create_task(service.reply(event()))
        await started.wait()
        with pytest.raises(DeliveryBusy):
            await service.reply(event())
        finish.set()
        await first
        await service.reply(event())
        assert wa.send_message.await_count == 1

    asyncio.run(scenario())


def test_cache_expiry_and_capacity_are_bounded():
    async def scenario():
        now = [0]
        wa = AsyncMock()
        service = ReplyService(wa, clock=lambda: now[0], capacity=2, ttl=10)
        await service.reply(event("one"))
        await service.reply(event("two"))
        await service.reply(event("three"))
        assert len(service.completed) == 2
        assert "one" not in service.completed
        now[0] = 11
        await service.reply(event("two"))
        assert wa.send_message.await_count == 4
        assert len(service.completed) == 1

    asyncio.run(scenario())


def test_cancelled_send_releases_claim():
    async def scenario():
        started = asyncio.Event()

        async def send(**kwargs):
            started.set()
            await asyncio.Event().wait()

        wa = AsyncMock()
        wa.send_message.side_effect = send
        service = ReplyService(wa)
        task = asyncio.create_task(service.reply(event()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.in_flight
        assert not service.completed
        wa.send_message.side_effect = None
        await service.reply(event())
        assert "one" in service.completed

    asyncio.run(scenario())
