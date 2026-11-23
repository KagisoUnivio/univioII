# univioII

A stateless WhatsApp guidance API built with FastAPI and PyWa's async client.
Forms are replaced by short chat menus. RDS PostgreSQL supplies a durable delivery
inbox and optional student matching profiles. The older `univio` project is
the reference for the student journey.

## Local setup

See [the applicant journey and AWS upload setup](docs/applicant-journey.md)
for the document upload flow, database seed commands and future application
automation plan.

See [student onboarding and matching](docs/matching.md) for the resumable
academic profile, programme and funding screening, and synthetic matching seeds.
The [legacy migration tracker](docs/legacy-parity.md) records which old app
features are available in this repository and which still need integration.

Create and activate a virtual environment, then install the local development
tooling:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pre-commit
.\.venv\Scripts\pre-commit.exe install --install-hooks --hook-type pre-commit --hook-type pre-push
```

Install application and test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Set `WHATSAPP_APP_SECRET` to your Meta app secret, and set independently generated
`WHATSAPP_VERIFY_TOKEN` and `API_TOKEN` values (at least 32 characters each).
Also set `WHATSAPP_ACCESS_TOKEN` to your Meta system-user access token with the
permissions needed to send WhatsApp messages, and `WHATSAPP_PHONE_ID` to your
numeric Meta phone-number ID (not the telephone number).
Generate each token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Set these in your local shell environment; the app does not automatically read
`.env` files. Never commit actual values. Missing configuration prevents startup.

Start the HTTP server locally:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m univio
```

For durable local testing, set `DATABASE_URL` to a dedicated local PostgreSQL
database, run `python -m univio.migrate` once with its DDL credential, and start
`python -m univio.worker` in a second terminal with the same src path. The API
saves events; the worker sends replies. Without DATABASE_URL, only local
development mode sends inline.

For deployed staging and production, set `APP_ENV=production`, DATABASE_URL and
DATABASE_CA_FILE. Production refuses missing database configuration and requires
verified TLS. See [the production runbook](docs/production.md) before creating AWS
resources or assigning database privileges.

| Endpoint | Purpose | Authentication |
|---|---|---|
| `GET /health` | Minimal health check | Public |
| `GET /ready` | Database/schema readiness (ALB check) | Public |
| `GET /api/v1/status` | Authenticated service status | `Authorization: Bearer <API_TOKEN>` |
| `GET /api/v1/delivery` | Aggregate inbox counts | `Authorization: Bearer <API_TOKEN>` |
| `GET /webhook` | Meta callback verification | `hub.mode=subscribe`, matching `hub.verify_token`, `hub.challenge` |
| `POST /webhook` | Verify and durably accept events | Meta `X-Hub-Signature-256` over the exact request body |

Configure Meta's callback as `https://<your-domain>/webhook` with the same verify
token. Subscribe to the `messages` webhook field. The app secret validates POST
signatures; the verify token alone does not authenticate POST requests. Use
Meta's test number and approved recipients for your first staging tests.

Send `hi` to see **Find my matches**, **Explore options**, and **Get help**.
Each screen has at most three reply buttons and matching text commands. `menu`,
`back`, `cancel`, and `stop` return to the main menu. Explore as a guest or
provide marks to get programme and funding screening when matching is enabled.
Old form submissions recover to chat choices without reading their answers.
Programme and funding results screen eligibility using the reviewed catalogue.
The institution or funding provider makes the final decision. The app also
supports optional private document intake. Full registration, personalised PDFs,
AI chat, and application submission are future features.

In database mode HTTP 200 means eligible events committed to the inbox (or were
intentionally ignored), not that a reply was sent. Duplicate events have one
durable row. Workers claim/retry replies across restarts; statuses, other numbers
and events at least 23 hours old are ignored. Recipients are cleared at terminal
outcomes and deduplication records expire after eight days. A crash after Meta
accepted a send can still cause a duplicate reply; there is no exactly-once claim.

Bodies are limited to 1 MiB, invalid signatures are rejected, and API docs are
disabled. Tests cover authentication, navigation, signatures, concurrency and retries:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Set TEST_DATABASE_URL to an isolated PostgreSQL database whose name ends in
`_test` to include real database/lease integration tests. The tests clear its
inbox; never point this variable at application data. CI supplies its own
PostgreSQL service and executes those tests on every PR.

For ECS, run separate API and worker services using the same image digest.
The API exposes port 8000 with an ALB `/ready` check; the worker overrides the
command to `python -m univio.worker` and needs no inbound access. Run migrations
as a one-off task before rollout. Inject secrets using Secrets Manager and keep
RDS private. The runbook covers TLS certificates, roles, backup/restore, alarms,
deployment and rollback. The publishing workflows push scanned images to ECR;
automatic ECS migration/rollout is not yet configured.

Read [the code walkthrough](docs/code-walkthrough.md) for a module-by-module guide,
[architecture](docs/architecture.md) for delivery guarantees and release gates,
[production setup](docs/production.md) for AWS configuration, and
[skills.md](skills.md) for the project's engineering rules.

## Code quality with Ruff

Ruff is the project's Python linter and formatter. Its configuration is in
[`.pre-commit-config.yaml`](.pre-commit-config.yaml).

After the one-time hook installation, Ruff runs automatically before every
commit and push. The hooks:

- check Python code for common errors and automatically apply safe fixes;
- format Python files consistently; and
- stop the commit or push if a remaining issue must be fixed manually.

Run all local checks manually at any time:

```powershell
.\.venv\Scripts\pre-commit.exe run --all-files
```

Run only Ruff's lint check:

```powershell
.\.venv\Scripts\ruff.exe check .
```

Local hooks are a fast feedback loop, but they can be bypassed. GitHub Actions
reruns the quality checks on pull requests, which is the final merge gate.

## Delivery workflow

The repository uses protected branches and pull requests:

```text
feature branch → pull request to dev → staging image pushed to Amazon ECR
dev → pull request to main → production deployment workflow
```

The pull-request validation workflow includes Python quality checks, a Docker
build, Semgrep, TruffleHog, Trivy, and CodeQL security analysis. Deployment
workflows use environment-scoped configuration and short-lived AWS credentials
through GitHub OIDC; no AWS access keys are stored in the repository.

## Security basics

- Never commit `.env` files, API keys, passwords, certificates, or private keys.
- Keep GitHub and AWS credentials in their respective secret or environment
  settings.
- Make changes on a feature branch and submit a pull request rather than
  pushing directly to `dev` or `main`.
