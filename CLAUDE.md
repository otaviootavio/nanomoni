# NanoMoni — Claude Code Instructions

## Development workflow

There are two test tiers with different requirements. Always identify which tier before running tests.

### Use-case tests (no services needed)

```bash
poetry run pytest tests/use_cases
```

These use in-memory implementations. Run freely — no Redis, no Docker, no running services.

### E2E tests (services required)

```bash
poetry run pytest -m e2e tests/e2e
```

**Before running E2E tests, all four of the following must be up:**

| Service | Port | Start command |
|---------|------|---------------|
| redis-vendor | 6379 | `docker compose up -d redis-vendor` |
| redis-issuer | 6380 | `docker compose up -d redis-issuer` |
| vendor API | 8000 | `source envs/vendor.env.dev.sh && poetry run python -m nanomoni.main` |
| issuer API | 8001 | `source envs/issuer.env.dev.sh && poetry run python -m nanomoni.issuer_main` |

A hook will automatically block the pytest command and list what is missing if any service is down.

### Code → reload → test flow

After editing any file under `src/nanomoni/`, uvicorn must reload before tests reflect the change.

**When the dev services are running**, a hook automatically waits for the vendor to come back up after each file edit and injects a confirmation message. Do not run tests until that confirmation arrives.

**When only running use-case tests** (no services started), edits take effect immediately — no wait needed.

## Running linting / type checks

```bash
bash scripts/lint.sh          # ruff
poetry run mypy src/nanomoni  # type checker
```

These never require running services.

## Project structure highlights

- `src/nanomoni/` — all application source code
- `tests/use_cases/` — fast unit tests, in-memory only
- `tests/e2e/` — end-to-end tests, require all services
- `tests/bug/` — regression tests for documented bugs
- `envs/` — environment variable scripts (`*.env.dev.sh` = local dev, `*.env.sh` = Docker)
- `.claude/hooks/` — hook scripts enforcing the dev workflow above
