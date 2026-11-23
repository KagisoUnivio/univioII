"""HTTP boundary and application composition; business copy lives elsewhere."""

import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Error as DatabaseError
from psycopg_pool import PoolTimeout
from pywa_async import WhatsApp
from pywa_async.errors import WhatsAppError

from univio.config import Settings
from univio.delivery import DeliveryBusy, ReplyService
from univio.events import parse_events
from univio.inbox import Inbox

MAX_WEBHOOK_BYTES = 1024 * 1024


def create_app(
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    inbox: Inbox | None = None,
) -> FastAPI:
    """Build isolated dependencies; transport injection keeps tests off Meta."""
    settings = settings or Settings.from_environment()
    inbox = inbox or (Inbox(settings.database) if settings.database else None)
    session = httpx.AsyncClient(
        timeout=5,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=20),
        transport=transport,
        follow_redirects=False,
    )
    wa = WhatsApp(
        phone_id=settings.phone_id,
        token=settings.access_token,
        session=session,
        verify_token=settings.verify_token,
        app_secret=settings.app_secret,
        validate_updates=True,
    )
    replies = ReplyService(wa)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            if inbox:
                await inbox.open()
            yield
        finally:
            if inbox:
                await inbox.close()
            await session.aclose()

    app = FastAPI(
        title="Univio API",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), settings.api_token.encode()
        ):
            raise HTTPException(
                401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/health")
    async def health():
        """Liveness only; deliberately disclose no dependency or secret details."""
        return {"status": "ok"}

    @app.get("/api/v1/status", dependencies=[Depends(authenticate)])
    async def status():
        return {
            "service": "univio",
            "mode": "durable-chat" if inbox else "development-inline",
        }

    @app.get("/ready")
    async def ready():
        """Use for ALB health: verify database availability and migration state."""
        if inbox:
            try:
                await inbox.ready()
            except (DatabaseError, PoolTimeout):
                raise HTTPException(503, "Not ready") from None
        return {"status": "ready"}

    @app.get("/api/v1/delivery", dependencies=[Depends(authenticate)])
    async def delivery_status():
        """Aggregate counts only; no recipient or message information."""
        if not inbox:
            return {"mode": "development-inline"}
        try:
            return await inbox.counts()
        except (DatabaseError, PoolTimeout):
            raise HTTPException(503, "Delivery status unavailable") from None

    @app.get("/webhook")
    async def verify_webhook(request: Request):
        """Perform Meta's subscription challenge without echoing failed tokens."""
        query = request.query_params
        if query.get("hub.mode") != "subscribe" or not query.get("hub.challenge"):
            raise HTTPException(400, "Invalid verification request")
        content, code = await wa.webhook_challenge_handler(
            vt=query.get("hub.verify_token"), ch=query["hub.challenge"]
        )
        return PlainTextResponse(content, status_code=code)

    @app.post("/webhook")
    async def receive_webhook(request: Request):
        """Authenticate before parsing; production acknowledges committed inbox work."""
        if (
            request.headers.get("content-type", "").split(";")[0].lower()
            != "application/json"
        ):
            raise HTTPException(415, "Expected application/json")
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_WEBHOOK_BYTES:
                        raise HTTPException(413, "Webhook body too large")
                    body.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "Request timed out") from None
        raw = bytes(body)
        if await wa.webhook_update_validator(
            update=raw, hmac_header=request.headers.get("x-hub-signature-256")
        ):
            raise HTTPException(401, "Invalid webhook signature")
        try:
            events = parse_events(raw, settings.phone_id)
        except ValueError:
            raise HTTPException(400, "Invalid webhook envelope") from None
        now = time.time()
        events = [event for event in events if 0 <= now - event.timestamp < 23 * 3600]
        if inbox:
            try:
                await inbox.accept(events, settings.phone_id)
            except (DatabaseError, PoolTimeout):
                raise HTTPException(
                    503,
                    "Acceptance unavailable; retry later",
                    headers={"Retry-After": "5"},
                ) from None
            return PlainTextResponse("ok")
        try:
            async with asyncio.timeout(15):
                for event in events:
                    await replies.reply(event)
        except (DeliveryBusy, TimeoutError, httpx.HTTPError, WhatsAppError):
            # No raw provider errors, identifiers, tokens or message text in logs/responses.
            raise HTTPException(
                503, "Reply unavailable; retry later", headers={"Retry-After": "5"}
            ) from None
        return PlainTextResponse("ok")

    return app
