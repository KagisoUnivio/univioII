# Applicant journey and release plan

The first release guides applicants from study exploration to entry requirements,
application preparation and document intake. A student can type `documents` at
any time or open it from Application prep or Get help. The WhatsApp upload
instructions ask for one file and one caption per submission. The categories
are applicant ID (`id`), matric results (`matric`) and Grade 11 results
(`grade11`). Use the institution's official checklist to decide which items
are needed. Guardian records and financial evidence are outside this intake.

Try it in staging with a synthetic PDF, with the caption `matric`. Try a file
with a missing caption or incorrect format and check that the correction is
clear. A successful receipt means the file entered quarantine. It does not
mean the document is genuine, readable, approved or sent to a university.

## How the upload works

1. The signed webhook identifies the attachment by its Meta media ID. The inbox
   retains the recognized caption category and media ID until processing ends.
2. The worker uses PyWa to resolve metadata, then streams bytes from the
   allowlisted Meta HTTPS host with redirects disabled. Size, MIME type and
   file signature must agree with supported formats. These checks do not scan
   malware or establish document authenticity.
3. The worker writes to `quarantine/<event key>` using a conditional S3 PUT.
   It stores a receipt in PostgreSQL with a keyed applicant identifier, category
   and object metadata. The original filename and caption text are discarded.
4. The worker sends a receipt. Reprocessing checks for the existing receipt.
   S3 and PostgreSQL commit separately, so a failed receipt commit can leave an
   orphaned object. Use quarantine lifecycle expiration and reconcile orphaned
   objects. WhatsApp acknowledgement can still duplicate on uncertain sends.

## AWS rollout

- Apply migration 002 before starting this API or worker. Grant the worker
  SELECT and INSERT on `document_intake` in addition to the inbox permissions.
  The API needs only the inbox. Run catalogue seeds with a separate data owner.
- Create a separate private S3 bucket per environment with Block Public Access,
  bucket owner enforced, TLS-only bucket policy, default SSE-KMS, and a
  retention rule for the quarantine prefix. If versioning is enabled, apply
  retention to noncurrent versions too. Set a matching receipt-retention and
  deletion process in RDS, including backup retention.
- Give the ECS **worker task role** `s3:PutObject` on its quarantine prefix
  and the KMS permissions required for that write. Keep the upload role
  write-only. Use an S3 endpoint or approved egress; the worker also needs
  HTTPS access to Meta. Give the ECS execution role access to the new Secrets
  Manager entry and inject `DOCUMENT_OWNER_SECRET` (an independent random
  secret of at least 32 characters). Set `DOCUMENT_BUCKET` on the worker to
  enable intake. Protect the owner key across releases: rotating it changes
  applicant identifiers unless you explicitly plan the migration.
- Enable GuardDuty Malware Protection for the prefix and enable result
  tagging before uploading. Alert on threats, skipped/failed scans and missing
  results. No app route currently reads quarantine. Before building a reader,
  restrict S3 reads (including version reads if granted) to objects tagged
  `GuardDutyMalwareScanStatus=NO_THREATS_FOUND`. Only the scanner may write
  that tag. Validate this with IAM and live staging tests.
- Before collecting real ID documents, review notices, minors' participation,
  collection authorization, contact/deletion paths and retention with your
  privacy team. The chat prompt requests permission to store a copy. A complete
  consent and deletion workflow still needs to be built and verified.

See [GuardDuty tag-based access control](https://docs.aws.amazon.com/guardduty/latest/ug/tag-based-access-s3-malware-protection.html)
and [the ECS and RDS runbook](production.md).

## Seed the catalogue

After migrations, run the reference seed as the catalogue owner:

```text
psql -X -v ON_ERROR_STOP=1 -f seeds/001_universities.sql
```

Configure the connection via approved PostgreSQL client settings. The SQL is
repeatable and leaves existing rows intact. Run `seeds/002_demo_catalog.sql`
only against an isolated database ending in `_test`. It contains an invented
institution and programme, with no applicant data. Production programme imports
still need reviewed official sources, verification dates and a policy for stale
entries. The catalogue schema and seeds are available for that import. Current
WhatsApp guidance remains general.

## Future application automation

Start with one university that authorizes the integration. Build a real draft
application and document checklist for that university, then add a review screen
showing the exact institution, programme, intake year and files. Capture explicit
submission approval for that revision and keep one stable idempotency key per
approved application. Require fresh approval after meaningful edits.

The future automation worker should get scoped access to verified files and
credentials, preserve receipts and report whether a submission succeeded, needs
attention, or has an uncertain outcome. Send uncertain outcomes to a human
instead of automatically resubmitting. Use official APIs where available and
stop for institution login challenges, payment or additional applicant approval.
The current intake implements no application submission or portal automation.
