# RDS and ECS production runbook

Code is prepared for **RDS PostgreSQL**. Confirm that engine before provisioning;
MySQL/MariaDB require a different driver and inbox implementation. No AWS
resources are created or changed by these repository edits.

## 1. Provision isolated environments

Use separate staging and production databases/credentials and ECS services.
Create PostgreSQL in private subnets with public access disabled. Enable storage
encryption, automated backups/PITR, deletion protection and an appropriate
maintenance window. Choose Multi-AZ for production availability and rehearse a
restore; Multi-AZ is not a backup. Restrict DB port 5432 ingress to the ECS task
security group, never the public internet. Budget RDS connections as five per
API/worker task plus migration/administration headroom.

Use the RDS endpoint hostname, not an IP/custom alias that fails certificate
hostname verification. Enforce server TLS (`rds.force_ssl`) and use the current
[AWS CA bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html).
The Dockerfile downloads the public Stockholm (`eu-north-1`) CA bundle during
the image build and verifies its pinned SHA-256 checksum. For that image, set
`DATABASE_CA_FILE=/app/certs/rds-ca.pem`. If AWS updates the bundle, verify the
new bundle and update the checksum before publishing a new image. For another
region, provide the appropriate bundle and configure its in-container path.

## 2. Configure secrets and roles

| Configuration | Placement |
|---|---|
| `APP_ENV=production` (also for deployed staging) | ECS task environment |
| `WHATSAPP_PHONE_ID` | ECS task environment |
| `DATABASE_CA_FILE` | ECS task environment; file must be available in container |
| `DATABASE_URL` | Secrets Manager; inject into API and worker |
| `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` | Secrets Manager |
| `WHATSAPP_ACCESS_TOKEN`, `API_TOKEN` | Secrets Manager |
| `MIGRATION_DATABASE_URL` | Separate Secrets Manager secret; migration job only |

Example DATABASE_URL shape (supply real values privately; URL-encode passwords):

```text
postgresql://univio_runtime:<encoded-password>@<rds-endpoint>:5432/univio
```

Production overrides transport parameters with verify-full and bounded timeouts.
There is no automatic `.env` loading. Rotate credentials using new secret versions
and an ECS rollout; existing tasks do not automatically reload environment values.

Keep these roles separate:

- GitHub deployment role: OIDC trust scoped to repository/environment, ECR push;
  later ECS rollout rights scoped to the services and exact passable task roles.
- ECS task execution role: ECR pull, log delivery and access only to required
  secret ARNs plus their KMS keys if applicable.
- API task role: no AWS API permissions are required. For optional document
  intake, give the worker task role scoped S3/KMS write permissions as described
  in the [applicant journey](applicant-journey.md).
- PostgreSQL migration login: DDL ownership of application schema.
- PostgreSQL runtime login: CONNECT, schema USAGE and SELECT/INSERT/UPDATE/DELETE
  on inbox only; no CREATE, ALTER, DROP, superuser or migration-ledger writes.

The current Settings loader requires all Meta/API variables for API and worker;
do not grant either service the migration credential. Additional per-process
secret narrowing can follow when startup configurations are split.

After creating the runtime login securely and running migrations as the owner,
grant it privileges (adapt names using an administrator; no password belongs in
this script):

```sql
GRANT CONNECT ON DATABASE univio TO univio_runtime;
GRANT USAGE ON SCHEMA public TO univio_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.inbox TO univio_runtime;
```

## 3. Run the migration explicitly

In an isolated ECS one-off task using the new image, private networking and the
migration secret, run:

```text
python -m univio.migrate
```

Inspect its exit code/logs before continuing. Do not run DDL from the API or
worker startup and do not give GitHub direct public access to RDS. Take a
recoverable backup before risky schema changes. Use additive migrations that
remain compatible with the prior app version for safe rollback.

## 4. Deploy two ECS services

Use the same **image digest** for both services, not a mutable latest tag.

| Service | Container command | Health |
|---|---|---|
| API | Image default (`python -m univio --host 0.0.0.0 --port 8000`) | ALB GET `/ready`; `/health` for liveness |
| Worker | `python -m univio.worker` | Essential process, ECS task health and CloudWatch worker/queue alarms |

Start with one worker; database claims permit later scaling. Give tasks at least
30 seconds to stop gracefully. Run tasks without root, with a read-only root
filesystem where compatible with your logging/runtime setup, and permit ingress
to API port 8000 only from the ALB security group. Workers need no inbound access.
Provide private-subnet egress to Meta and ECR/Secrets Manager/logs using the
appropriate NAT/endpoints. Set log retention explicitly.

Use HTTPS with ACM, Route 53/custom DNS and ALB. Add WAF/request-rate controls.
Protect API bearer tokens in the caller and do not apply that token rule to
Meta's signed webhook route. Disable/redact logging that captures verification
query strings or payloads. `/ready` proves DB/schema health, not worker progress:
alarm separately on pending queue age/count, dead jobs, absent workers, database
connections/storage, API 5xx and ALB unhealthy targets. The protected
`/api/v1/delivery` endpoint exposes aggregate counts; configure your monitoring
collector/alarms rather than assuming they exist automatically.

## 5. Release and rollback

Dev/main currently build, scan and publish images through shared GitHub Actions.
They intentionally do not claim to deploy ECS. Configure each GitHub Environment
with AWS_REGION, AWS_ROLE_ARN and ECR_REPOSITORY; retain branch restrictions and
required production reviewers. Use separate production and staging role trust.

For each release: run all PR checks, publish a scanned image, record its digest,
run the migration task, update the API and worker task definitions to that digest,
roll out in staging, run signed webhook smoke tests, then approve production.
Keep the last known-good task definitions. Roll back both services to that digest
if needed; do not blindly downgrade the database. Automated ECS rollout is the
next infrastructure task once cluster, service, task-role and network IDs are
known. Do not paste credentials in chat to configure it.

## 6. Acceptance checks before go-live

- Verify Meta's challenge/replies through the actual HTTPS domain using approved
  test recipients. Confirm expired tokens and wrong signatures fail safely.
- Send the same event concurrently to multiple API tasks and restart a worker
  after claim; check only one durable row and lease recovery.
- Simulate database and Meta outages, rate limits and exhausted attempts. Confirm
  queue drain and alert delivery after recovery. A timeout after accepted sends
  can still produce duplicate replies; document this external boundary.
- Run realistic load tests, confirm pool/concurrency limits and tune timeouts.
- Restore RDS into an isolated environment and verify recovery procedures.
- Review the eight-day tombstone/backup retention and privacy policy. No profiles
  or documents are collected, but pending recipients are personal data.
- Verify container scan, dependencies, secret rotation, least-privilege logins,
  rollback, production approvals, alarms and an incident owner.

This checklist is not yet executed against AWS. Local tests validate application
and PostgreSQL behavior, not your VPC, RDS TLS, Meta permissions or ECS rollout.
