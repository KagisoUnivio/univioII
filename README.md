# univioII

A small Python application being built incrementally with automated quality and
security checks from the start.

## Local setup

Create and activate a virtual environment, then install the local development
tooling:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pre-commit
.\.venv\Scripts\pre-commit.exe install --install-hooks --hook-type pre-commit --hook-type pre-push
```

Run the application with:

```powershell
.\.venv\Scripts\python.exe main.py
```

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
