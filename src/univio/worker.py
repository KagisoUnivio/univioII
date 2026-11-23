"""Durable inbox consumer. Run separately: python -m univio.worker."""

import asyncio
import logging
import os
import signal
import time

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from psycopg import Error as DatabaseError
from psycopg_pool import PoolTimeout
from pywa_async import WhatsApp
from pywa_async.errors import ThrottlingError, WhatsAppError

from univio.config import Settings
from univio.conversation import SCREENS
from univio.delivery import ReplyService
from univio.documents import DocumentIntake
from univio.events import Event
from univio.inbox import Inbox
from univio.onboarding import Onboarding, profile_secret
from univio.runtime import run_async

logger = logging.getLogger(__name__)


async def process_one(
    inbox: Inbox,
    replies: ReplyService,
    phone_id: str,
    documents: DocumentIntake | None = None,
    onboarding: Onboarding | None = None,
) -> bool:
    """Bound processing below the lease duration; classify provider failures."""
    job = await inbox.claim(phone_id)
    if not job:
        return False
    try:
        async with asyncio.timeout(15):
            screen = None
            if documents and job["kind"] == "upload":
                screen = await documents.receive(job)
            elif documents and job["command"] == "upload":
                screen = SCREENS["upload"]
            elif onboarding:
                screen = await onboarding.respond(job)
            await replies.reply(
                Event(
                    job["event_key"],
                    job["recipient"],
                    job["event_timestamp"],
                    job["command"],
                    job["kind"],
                ),
                screen=screen,
            )
    except WhatsAppError as exc:
        # 429/5xx retry; other explicit provider errors require human correction.
        permanent = not isinstance(exc, ThrottlingError) and (
            exc.status_code is not None
            and 400 <= exc.status_code < 500
            and exc.status_code != 429
        )
        await inbox.finish(job, error="provider", permanent=permanent)
        logger.warning("reply_failed category=provider permanent=%s", permanent)
    except (httpx.HTTPError, TimeoutError, BotoCoreError, ClientError):
        await inbox.finish(job, error="transport")
        logger.warning("reply_failed category=transport")
    else:
        await inbox.finish(job)
        logger.info("reply_completed")
    return True


async def run():
    settings = Settings.from_environment()
    if settings.database is None:
        raise ValueError("Worker requires DATABASE_URL")
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    inbox = Inbox(settings.database)
    secret = profile_secret()
    onboarding = Onboarding(inbox.pool, secret) if secret else None
    try:
        await inbox.open()
        async with httpx.AsyncClient(timeout=5) as session:
            wa = WhatsApp(
                phone_id=settings.phone_id, token=settings.access_token, session=session
            )
            replies = ReplyService(wa)
            bucket = os.environ.get("DOCUMENT_BUCKET")
            owner_secret = os.environ.get("DOCUMENT_OWNER_SECRET", "")
            documents = None
            if bucket:
                if len(owner_secret) < 32:
                    raise ValueError(
                        "Uploads require an independent DOCUMENT_OWNER_SECRET"
                    )
                s3 = boto3.client(
                    "s3",
                    config=Config(
                        connect_timeout=3,
                        read_timeout=5,
                        retries={"total_max_attempts": 1},
                    ),
                )
                documents = DocumentIntake(
                    inbox, wa, session, s3, bucket, owner_secret, settings.access_token
                )
            maintenance_at = 0.0
            while not stop.is_set():
                try:
                    if time.monotonic() >= maintenance_at:
                        await inbox.maintain()
                        maintenance_at = time.monotonic() + 60
                    processed = await process_one(
                        inbox, replies, settings.phone_id, documents, onboarding
                    )
                except (DatabaseError, PoolTimeout):
                    logger.error("worker_database_unavailable")
                    processed = False
                if not processed:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=1)
                    except TimeoutError:
                        pass
    finally:
        await inbox.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    run_async(run())
