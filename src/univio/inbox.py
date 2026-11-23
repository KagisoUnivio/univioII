"""PostgreSQL durable inbox: transactional acceptance and leased worker claims."""

import hashlib
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from univio.career import QUIZ
from univio.cart import cart_command
from univio.config import DatabaseConfig
from univio.conversation import ALIASES, DOCUMENT_TYPES, SCREENS
from univio.events import Event
from univio.matching import canonical_marks
from univio.onboarding import profile_secret


class Inbox:
    def __init__(self, config: DatabaseConfig):
        self.matching_enabled = bool(profile_secret())
        self.pool = AsyncConnectionPool(
            config.url,
            kwargs={**config.connection_kwargs(), "row_factory": dict_row},
            min_size=1,
            max_size=5,
            max_waiting=20,
            timeout=5,
            open=False,
        )

    async def open(self):
        await self.pool.open(wait=True, timeout=10)
        await self.ready()

    async def close(self):
        await self.pool.close()

    async def ready(self):
        """Readiness requires the expected schema, not just an open socket."""
        async with self.pool.connection() as conn:
            await conn.execute(
                "SELECT event_key, lease_token, media_id FROM inbox LIMIT 0"
            )

    async def accept(self, events: list[Event], phone_id: str):
        """Commit all accepted events atomically; store no free-text input."""
        async with self.pool.connection() as conn:
            for event in events:
                key = hashlib.sha256(f"{phone_id}:{event.id}".encode()).hexdigest()
                command = (event.command or "").strip().casefold()
                command = ALIASES.get(command, command)
                allowed = DOCUMENT_TYPES if event.kind == "upload" else SCREENS
                if (
                    self.matching_enabled
                    and event.kind == "text"
                    and command.split(maxsplit=1)[:1] == ["marks"]
                    and command != "marks"
                ):
                    command = canonical_marks(command) or "marks-help"
                elif event.kind == "text" and command.startswith("quiz "):
                    command = command if QUIZ.fullmatch(command) else "career"
                elif (
                    self.matching_enabled
                    and event.kind in ("text", "selection")
                    and cart_command(command)
                ):
                    pass
                else:
                    command = command if command in allowed else None
                await conn.execute(
                    """INSERT INTO inbox (event_key, phone_id, recipient, event_timestamp, command, kind, media_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (event_key) DO NOTHING""",
                    (
                        key,
                        phone_id,
                        event.sender,
                        event.timestamp,
                        command,
                        event.kind,
                        event.media_id if command and event.kind == "upload" else None,
                    ),
                )

    async def claim(self, phone_id: str):
        """SKIP LOCKED supports multiple workers; token fences stale completions."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """UPDATE inbox SET state='processing', attempts=attempts+1,
                lease_until=now()+interval '60 seconds', lease_token=%s, updated_at=now()
                WHERE event_key=(SELECT event_key FROM inbox
                    WHERE phone_id=%s AND attempts < 5 AND
                    event_timestamp > extract(epoch from now())-82800 AND
                    ((state='pending' AND available_at<=now()) OR
                     (state='processing' AND lease_until<now()))
                    ORDER BY available_at FOR UPDATE SKIP LOCKED LIMIT 1)
                RETURNING *""",
                (uuid4(), phone_id),
            )
            return await cursor.fetchone()

    async def finish(self, job, *, error: str | None = None, permanent=False):
        """Clear recipient immediately on terminal outcomes; retain only a tombstone."""
        state = (
            "sent"
            if error is None
            else "dead"
            if permanent or job["attempts"] >= 5
            else "pending"
        )
        async with self.pool.connection() as conn:
            await conn.execute(
                """UPDATE inbox SET state=%s, recipient=CASE WHEN %s='pending' THEN recipient ELSE NULL END,
                media_id=CASE WHEN %s='pending' THEN media_id ELSE NULL END,
                command=CASE WHEN %s='pending' THEN command ELSE NULL END,
                error_kind=%s, lease_until=NULL, lease_token=NULL,
                available_at=now()+(%s * interval '1 second'), updated_at=now()
                WHERE event_key=%s AND lease_token=%s AND state='processing'""",
                (
                    state,
                    state,
                    state,
                    state,
                    error,
                    min(300, 2 ** job["attempts"]),
                    job["event_key"],
                    job["lease_token"],
                ),
            )

    async def maintain(self):
        """Expire unsendable work; retain dedup tombstones for eight days."""
        async with self.pool.connection() as conn:
            await conn.execute("""UPDATE inbox SET state='dead', recipient=NULL, media_id=NULL, command=NULL, error_kind='expired',
                lease_token=NULL, lease_until=NULL, updated_at=now()
                WHERE state IN ('pending','processing') AND
                (event_timestamp <= extract(epoch from now())-82800 OR
                 (state='processing' AND lease_until<now() AND attempts>=5))""")
            await conn.execute(
                "DELETE FROM inbox WHERE state IN ('sent','dead') AND updated_at<now()-interval '8 days'"
            )
            if self.matching_enabled:
                await conn.execute(
                    "DELETE FROM matching_profile WHERE updated_at<=now()-interval '30 days'"
                )

    async def counts(self):
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT state, count(*) AS count FROM inbox GROUP BY state"
            )
            return {row["state"]: row["count"] for row in await cursor.fetchall()}
