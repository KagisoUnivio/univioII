"""Production startup, durable HTTP acceptance and worker policy boundaries."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from test_main import SETTINGS, envelope, post_event

from univio.app import create_app
from univio.config import DatabaseConfig
from univio.worker import process_one


def test_production_cannot_use_inline_delivery():
    with pytest.raises(ValueError, match="Production requires"):
        replace(SETTINGS, environment="production")
    with pytest.raises(ValueError, match="Remote databases require"):
        DatabaseConfig("postgresql://user@database.example/app")


def test_production_overrides_insecure_dsn_tls(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("certificate placeholder for configuration validation")
    config = DatabaseConfig(
        "postgresql://user@database.example/app?sslmode=disable", "production", str(ca)
    )
    assert config.connection_kwargs()["sslmode"] == "verify-full"
    assert config.connection_kwargs()["sslrootcert"] == str(ca)
    with pytest.raises(ValueError, match="DATABASE_CA_FILE"):
        DatabaseConfig("postgresql://user@database.example/app", "production")


def test_durable_acceptance_commits_without_sending():
    inbox = AsyncMock()
    inbox.counts.return_value = {"pending": 1}
    transport = httpx.MockTransport(
        lambda request: pytest.fail("API must not send in durable mode")
    )
    with TestClient(create_app(SETTINGS, transport=transport, inbox=inbox)) as client:
        assert post_event(client, envelope()).status_code == 200
        inbox.accept.assert_awaited_once()
        assert client.get("/ready").status_code == 200
        assert client.get("/api/v1/delivery").status_code == 401
        inbox.accept.side_effect = OperationalError("private connection detail")
        response = post_event(client, envelope())
        assert response.status_code == 503
        assert "private connection detail" not in response.text
        inbox.ready.side_effect = OperationalError("unavailable")
        assert client.get("/ready").status_code == 503
    inbox.close.assert_awaited_once()


def test_worker_success_and_transport_retry():
    async def scenario():
        inbox, replies = AsyncMock(), AsyncMock()
        job = {
            "event_key": "event",
            "recipient": "27821234567",
            "event_timestamp": 0,
            "command": "menu",
            "kind": "text",
        }
        inbox.claim.return_value = job
        assert await process_one(inbox, replies, "123")
        inbox.finish.assert_awaited_once_with(job)
        inbox.finish.reset_mock()
        replies.reply.side_effect = httpx.ReadTimeout("private error")
        assert await process_one(inbox, replies, "123")
        inbox.finish.assert_awaited_once_with(job, error="transport")
        inbox.claim.return_value = None
        assert not await process_one(inbox, replies, "123")

    asyncio.run(scenario())
