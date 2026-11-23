"""Explicit, versioned PostgreSQL migrations; never run automatically on startup."""

import hashlib
import os
from pathlib import Path

from psycopg import AsyncConnection

from univio.config import DatabaseConfig
from univio.runtime import run_async


async def migrate(config: DatabaseConfig) -> None:
    """Serialize migrators and reject edits to already-applied migrations."""
    async with await AsyncConnection.connect(
        config.url, **config.connection_kwargs()
    ) as conn:
        await conn.execute("SELECT pg_advisory_xact_lock(741852963)")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, checksum text NOT NULL)"
        )
        for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            cursor = await conn.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s",
                (path.name,),
            )
            row = await cursor.fetchone()
            if row:
                if row[0] != checksum:
                    raise RuntimeError(
                        "Applied migration checksum changed; add a new migration instead"
                    )
                continue
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations VALUES (%s, %s)", (path.name, checksum)
            )


if __name__ == "__main__":
    # Keep DDL credentials separate from the runtime account.
    run_async(
        migrate(
            DatabaseConfig.from_environment(
                "MIGRATION_DATABASE_URL"
                if os.environ.get("MIGRATION_DATABASE_URL")
                else "DATABASE_URL"
            )
        )
    )
