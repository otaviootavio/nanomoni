---
name: nanomoni-dev-workflow
description: How to run the linter (ruff, mypy), use Poetry for dependencies and venv, and run each test suite (unit, use_cases, e2e, stress, bug). Use when setting up the project, running checks, or when the user asks about linting, Poetry, or tests.
---

# NanoMoni Dev Workflow

## Linter

The project uses **Ruff** (style + lint) and **Mypy** (static typing). Run everything via the script:

```sh
./scripts/lint.sh
```

Or run each step explicitly:

```sh
poetry run mypy src tests
poetry run ruff check src tests --fix
poetry run ruff format src tests
```

- **mypy**: Type-checks `src` and `tests`; config in `pyproject.toml` (`[tool.mypy]`). Uses pydantic plugin, strict options (`check_untyped_defs`, `disallow_untyped_defs`).
- **ruff check**: Lint + auto-fix on `src` and `tests`.
- **ruff format**: Format code (no separate config file; uses Ruff defaults).

Always run the linter from the repo root so paths resolve correctly.

---

## Poetry Setup

- **Python**: Project requires **Python 3.9** (bounded `<3.10.0` in `pyproject.toml`). Use pyenv: `pyenv install 3.9` then `pyenv local 3.9`.
- **Install deps**: `poetry install` (creates venv and installs all dependencies).
- **Run commands**: Use `poetry run <command>` so the project venv is used, e.g. `poetry run pytest ...`, `poetry run mypy ...`.
- **Venv path**: `poetry env info --path` — use this path when selecting the Python interpreter in the editor.
- **Packages**: Code lives under `src/nanomoni`; `[tool.poetry]` in `pyproject.toml` declares `packages = [{include = "nanomoni", from = "src"}]`.

No global Poetry config is required beyond having Poetry installed.

---

## Tests

All test commands assume you are in the repo root and use `poetry run pytest ...`.

### Unit tests (`tests/unit/`)

**Command:**

```sh
poetry run pytest tests/unit
```

**Purpose:** Fast, isolated tests for a single module or layer (crypto, validators, etc.). No services, no HTTP, no Redis. Use for algorithm correctness (e.g. Merkle trees, prover/verifier) and pure application logic (validators).

**Why they exist:** Quick feedback on core logic and invariants without starting Docker or APIs.

---

### Use case tests (`tests/use_cases/`)

**Command:**

```sh
poetry run pytest tests/use_cases
```

**Purpose:** Exercise business flows through use cases with **in-memory** implementations (no Docker, no real HTTP/Redis). They mirror many E2E stories but run in milliseconds.

**Why they exist:** Fast regression on full business flows (registration, open channel, payments, closure, tampering rejection) without infrastructure. Ideal for CI and local iteration.

---

### E2E tests (`tests/e2e/`)

**Command:**

```sh
poetry run pytest -m e2e tests/e2e
```

**Prerequisites:** Issuer API (port 8001), Vendor API (port 8000), Redis for issuer (6380), Redis for vendor (6379). Start services manually (e.g. via `docker compose` and `envs/*.env.sh`) before running.

**Purpose:** End-to-end verification over HTTP against real services. Covers happy paths, business rules (excessive/decreasing payments, empty channel closure), and security (tampered signatures, wrong keys, invalid PayWord/Paytree tokens).

**Why they exist:** Prove the integrated system (APIs + storage) behaves correctly; catch contract and deployment issues that unit/use-case tests cannot.

---

### Stress tests (inside `tests/e2e/`)

**Command:**

```sh
poetry run pytest -m stress tests/e2e
```

**Purpose:** Marked with `@pytest.mark.stress`; heavier load/attack scenarios (e.g. open/close PayWord attack). Same service prerequisites as E2E.

**Why they exist:** Validate behavior under load or specific attack patterns that are too slow or too heavy for the default E2E run.

---

### Bug tests (`tests/bug/`)

**Command:**

```sh
poetry run pytest tests/bug
```

**Purpose:** Document and guard against known bugs (e.g. first-payment index edge cases). See `tests/bug/BUG_REPORT.md` for descriptions.

**Why they exist:** Prevent regressions of documented bugs and keep a single place (code + BUG_REPORT) for the intended fix behavior.

---

## Quick reference

| Goal              | Command |
|-------------------|--------|
| Lint + typecheck  | `./scripts/lint.sh` |
| Unit only         | `poetry run pytest tests/unit` |
| Use cases only    | `poetry run pytest tests/use_cases` |
| E2E (services up)  | `poetry run pytest -m e2e tests/e2e` |
| Stress            | `poetry run pytest -m stress tests/e2e` |
| Bug regression    | `poetry run pytest tests/bug` |

The script `scripts/test.sh` runs E2E, use_cases, and unit in sequence; ensure services are up before using it if E2E is included.
