# Univio engineering rules

Apply these rules when changing this repository. Keep the implementation and its
documentation aligned; inspect existing code and tests before editing.

- Put runtime Python code in `src/univio/` and behavior tests in `tests/`.
- Use PyWa's async client for WhatsApp operations and webhook authentication.
  Keep HTTP concerns in `app.py`, validated configuration in `config.py`,
  conversation decisions/copy in `conversation.py`, and delivery in `delivery.py`.
- Apply DRY to repeated behavior and message content. Define an option once and
  derive its button and command help from it. Do not abstract unrelated behavior
  merely because it looks similar.
- Apply YAGNI and KISS: no speculative frameworks, service/repository layers,
  persistent sessions, AI calls or database writes without an actual requirement.
  RDS PostgreSQL is now in scope for a durable delivery inbox. Store only the
  delivery fields needed. For applicant uploads, allowlisted receipt metadata
  belongs in PostgreSQL and file bytes belong in private S3 quarantine. Keep
  raw webhook text and profiles out of the inbox. Production
  must use verified database TLS, explicit migrations and a separate worker.
- Keep functions cohesive, dependencies explicit and side effects at boundaries.
  Prefer pure conversation decisions that are easy to test.
- Program defensively at trust boundaries: validate configuration and payloads,
  bound body sizes/timeouts/cache growth, authenticate before processing, ignore
  unrelated phone numbers/statuses, and fail closed on missing secrets.
- Never hardcode live credentials or copy `.env`, private keys, customer data or
  database code from the reference project. Do not log user text or raw provider
  exceptions. Give clients safe, actionable errors.
- Replace form-heavy navigation with short chat journeys, at most three reply
  buttons per screen, text alternatives and a consistent route back to the menu.
  Do not imply that an application, profile or eligibility assessment was saved
  when no such backend exists.
- Suppress duplicate events by event identity, not message text: users may
  intentionally send the same text again. Bound caches and document their scope.
  Never claim exactly-once sending from a process-local cache.
- Test valid and rejected requests, conversation navigation, replay/concurrency,
  outbound failures and retry behavior without contacting real users.
- Run Ruff, tests and relevant build checks. Document architecture decisions,
  every module, setup, endpoints, configuration and operational limitations.
  Explain incomplete checks honestly; do not call a staging build production-ready
  without deployment, recovery, load and security validation.
- Preserve unrelated user edits. Changes go through PRs to protected dev/main;
  deployments use environment-scoped configuration and AWS OIDC.
- Make routine, reversible product decisions that advance the student journey.
  Keep academic discovery available before documents. Explain matching outcomes
  and publish only reviewed catalogue rules with an official source and intake.
