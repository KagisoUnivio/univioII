# Code walkthrough

Read this alongside [architecture](architecture.md), then use
[production.md](production.md) for environment setup. All runtime Python is under
`src/univio/`. The reference project is not a runtime dependency.

## Startup and configuration

`config.Settings` validates the five Meta/API settings, ensures API and
verification tokens differ, and reads `APP_ENV`. Secrets are excluded from repr.
`Settings.from_environment()` constructs `DatabaseConfig` only when DATABASE_URL
exists. In production mode a database is mandatory.

`DatabaseConfig` parses the libpq connection string and requires host/database.
Production additionally requires an existing CA file. `connection_kwargs()`
overrides TLS/connection/statement/lock timeouts so URL parameters cannot silently
disable verification. Development permits local unencrypted PostgreSQL; never
use development mode on your deployed RDS environment.

`python -m univio` calls `__main__.main()`, which creates a Uvicorn configuration
with no access logs, reload or proxy-header trust. It caps concurrency and keep-
alive, then uses `runtime.run_async()`. That helper selects a compatible loop for
Psycopg on Windows and leaves platform defaults intact elsewhere.

## HTTP composition: app.py

`create_app()` wires Settings, the HTTPX/PyWa client, reply service and optional
Inbox. Dependency injection is limited to transport/inbox overrides for tests.
The lifespan opens and checks the inbox before accepting traffic and closes
connections on shutdown. The API never auto-migrates a live database.

The response middleware sets no-store/nosniff. `authenticate()` compares a bearer
token in constant time. `/health` proves liveness, `/ready` checks database/schema
availability, `/api/v1/status` reports the configured delivery mode and
`/api/v1/delivery` returns aggregate inbox counts. Both `/api` routes are private.

`verify_webhook()` checks Meta's subscription query and delegates token/challenge
handling to PyWa. `receive_webhook()` bounds the body before authenticating its
exact bytes, parses the complete envelope, scopes and age-filters messages, then
awaits `Inbox.accept()`. Database failures return a safe 503 so Meta can retry.
Only local development without a DB uses the original inline-send path.

## Validation: events.py

The small Pydantic shapes mirror the Meta fields we use. `MetaModel` is strict
about types but accepts unrelated added fields. `parse_events()` validates the
complete batch before processing, ignores other numbers/status updates, and
returns small `Event` dataclasses. Missing text or selection IDs are invalid;
media and old form events map to recovery rather than reading their contents.

## Conversation: conversation.py

`Option` stores one command/label pair. `Screen` stores text and options;
`render()` derives text-command hints from the exact same options as buttons.
`SCREENS` is the shared catalog, `ALIASES` centralizes greetings/escape commands,
and `choose_screen()` resolves only known keys. Unknown input is never echoed
or turned into an AI request. Old forms recover to chat menus.

The journeys cover exploration, general entry-requirement guidance and help.
Application preparation and Help also lead to the document checklist. The
worker shows upload instructions only when intake is configured.
`back`, `cancel`, `stop` and `menu` return to the root; parent-category buttons
avoid requiring server-side navigation history. `stop` is not a persisted
marketing opt-out; this service has no proactive campaigns.

## Reply transport: delivery.py

`ReplyService.reply()` builds one screen and uses PyWa `send_message()` with
typed `Button` objects. A small process cache skips locally completed IDs and
tracks in-flight calls without holding locks during network I/O. It records
completion only after success and releases claims on cancellation/failure.
This is a local optimization; PostgreSQL is the durable source in production.

## Persistence: inbox.py

- `open()` explicitly starts the bounded pool and checks expected schema columns.
- `ready()` checks the actual inbox schema; `close()` releases the pool.
- `accept()` commits a whole batch in one transaction. Unique hashed identities
  deduplicate by event, not text. Only known catalog commands are persisted.
- `claim()` atomically selects/locks an eligible job and assigns a UUID lease
  token. Concurrent consumers skip already locked rows.
- `finish()` updates only the current lease, schedules a retry or records a
  terminal result, and clears recipient data on terminal outcomes.
- `maintain()` expires unsendable/exhausted work and removes old terminal records.
- `counts()` exposes aggregate processing states without recipient details.

SQL values are parameterized. No ORM or generic repository layer is needed for
the present inbox. Indexes cover claim scheduling and terminal retention.

## Worker: worker.py

`process_one()` claims work, bounds a PyWa send below the lease duration and
classifies failures into retryable transport/throttling/server errors or explicit
permanent provider errors. Only categories are logged, not raw exception text.
Unexpected programming failures propagate so ECS can restart the process; expired
leases allow recovery. A completion failure after a successful send remains a
potential duplicate-delivery boundary.

`run()` installs termination handling, opens the database/client, performs minute-
interval maintenance and drains jobs. Idle/database-unavailable periods wait one
second; termination stops new claims and permits the current bounded send to
complete. Configure ECS stopTimeout at least 30 seconds. Run it as a separate ECS
service using the same image with command `python -m univio.worker`.

## Schema changes: migrate.py and migrations/

`migrate()` uses one transaction and a PostgreSQL advisory lock. It creates the
migration ledger, verifies checksums and applies only unapplied numbered SQL
files. The CLI prefers `MIGRATION_DATABASE_URL`; use a separate DDL credential,
not the API/worker login. Never edit an applied SQL migration: add a new one.
`001_inbox.sql` creates the inbox and its two indexes without extensions.
`002_document_intake.sql` adds a temporary media reference, upload receipts,
and catalogue tables. See [the applicant journey](applicant-journey.md)
for `DocumentIntake`, S3 quarantine, and seed commands.

## Tests and build files

- `test_main.py`: HTTP auth, signature, limits, menu recovery, real PyWa request
  encoding with mocked Meta HTTP, inline retries and batched events.
- `test_conversation.py`: reachability, platform lengths and command recovery.
- `test_delivery.py`: local cache concurrency, cancellation and TTL/capacity.
- `test_production.py`: fail-closed production config, TLS overrides, committed
  acceptance without sending, safe database errors and worker retry behavior.
- `test_inbox.py`: real PostgreSQL migrations, concurrent acceptance/claims,
  lease recovery/fencing, retention, and full API-to-worker processing. It skips
  locally without TEST_DATABASE_URL; CI supplies a dedicated test database.
- `requirements*.txt`: runtime and development direct pins, not a transitive lock.
- `pyproject.toml`: src-aware test paths, test markers and Ruff settings.
- `Dockerfile`: one non-root image for API, migration job and worker.
- `.github/workflows/pr-validation.yml`: code/security checks with PostgreSQL.
- `publish-image.yml`: reusable image build/scan/push called from dev/main wrappers.
- `skills.md` and `AGENTS.md`: project rules and their discovery entry point.
