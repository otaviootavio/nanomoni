# NanoMoni

## Quickstart (pyenv + Poetry)

#### PAREI AQUI


1. Repositorio deveria ser merkle_tree_nodes_repository ao inves de estar relacionado com a primeira otimização
2. Talvez reduzir o tamanho do serviço para o paytree, está muito gordo
2.1 reduzir = adotar composição de classes

###

### Prerequisites

- [pyenv](https://github.com/pyenv/pyenv) installed
- [Poetry](https://python-poetry.org/docs/#installation) installed

### Setup Steps

1. **Install Python 3.9 using pyenv:**

   ```sh
   pyenv install 3.9
   pyenv local 3.9
   ```

2. **Verify Python version:**

   ```sh
   python --version  # Should output Python 3.9.x
   ```

3. **Install project dependencies with Poetry:**

   ```sh
   poetry install
   ```

4. **Activate the Poetry virtual environment (optional):**

   ```sh
   poetry env activate
   ```

   Or run commands with `poetry run`:

   ```sh
   poetry run python -m nanomoni.main
   ```

5. **Add the Python interpreter to VSCode**



Copy the path from Poetry environment for this project.

```sh
poetry env info --path
```

Open the command palette with <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>, type `Python: Select Interpreter` and add it.
---

## Local Development (fast reload)

Run the app natively with Poetry — no Docker rebuild cycle. Redis runs as a Docker sidecar; the app runs on the host with uvicorn `--reload` (event-driven via `watchfiles`, already included in `uvicorn[standard]`).

### 1) Start Redis sidecars

```sh
docker compose up -d redis-issuer redis-vendor
```

### 2) Run issuer and vendor (separate terminals)

```sh
# Terminal 1 — issuer on :8001
source ./envs/issuer.env.dev.sh && poetry run python -m nanomoni.issuer_main

# Terminal 2 — vendor on :8000
source ./envs/vendor.env.dev.sh && poetry run python -m nanomoni.main
```

File changes trigger an automatic reload in ~200 ms. No image rebuilds needed.

### 3) Stop Redis when done

```sh
docker compose stop redis-issuer redis-vendor
```

---

## Docker Compose Setup

Prereqs:
- Docker + Docker Compose v2 (`docker compose`)

### 1) Start observability

```sh
docker compose up -d alloy pyroscope cadvisor grafana prometheus
```

### 2) Copy environment variable examples

Copy the example environment files to create the actual environment files:

```sh
cp envs/example.client.sh envs/client.env.sh
cp envs/example.issuer.sh envs/issuer.env.sh
cp envs/example.vendor.sh envs/vendor.env.sh
```

### 3) Export runtime environment variables

This repo uses `envs/*.env.sh` scripts (they `export ...`, e.g. `issuer.env.sh`) so you can load all required variables into your shell:

```sh
source ./envs/issuer.env.sh
source ./envs/vendor.env.sh
source ./envs/client.env.sh
```

### 4) Build + run the services

Issuer and vendor will start their Redis dependencies via `depends_on`.

```sh
docker compose build

source ./envs/issuer.env.sh && docker compose up issuer -d --build
source ./envs/vendor.env.sh && docker compose up vendor -d --build
source ./envs/client.env.sh && docker compose up client -d --build
```

### Vendor worker ports

With `VENDOR_API_WORKERS=N` the vendor runs N single-worker servers on
consecutive ports from `VENDOR_API_PORT` (so `8000..8011` for the benchmark
layout), one listening socket each, instead of N workers sharing one socket. A
keep-alive connection is served end to end by the worker that accepted it, so the
port a client dials is the worker it reaches — which is what lets the load
generator spread itself evenly (`CLIENT_VENDOR_PORT_COUNT`) instead of leaving
the kernel to pile connections onto a few workers.

Only `8000` is published to the host; the rest of the range would collide with
the issuer on 8001 and the client's metrics on 8002. For the same reason the
local-dev and example env scripts keep `VENDOR_API_WORKERS=1`. See
[docs/worker-affinity-and-saturation.md](docs/worker-affinity-and-saturation.md)
for the reasoning and the measurements,
[docs/benchmark-ceiling-and-what-remains.md](docs/benchmark-ceiling-and-what-remains.md)
for where the ceiling ends up and what holds it, and [tuning.md](tuning.md) for the
core layout.

## Publishing Docker images

### Dead-simple (Docker Hub, single-arch, no buildx)

```sh
docker login
USERNAME=otaviootaviootavio ./scripts/publish-images.sh
```

This script always builds + pushes `:latest` for issuer/vendor/client.

### 5) Stop everything

```sh
docker compose down
```

## Running Tests

### Prerequisites

- Poetry installed (for dependency management)
- Docker + Docker Compose v2 (for E2E and stress tests)

### Installation

```sh
poetry install
```

### Running Tests

#### Use Case Tests (Fast, No Dependencies)

Use case tests are fast unit tests that test business logic directly through use cases, without requiring Docker, HTTP servers, or external services. They run in milliseconds and are ideal for rapid development feedback.

**No prerequisites required** - these tests use in-memory implementations.

```sh
# Run all use case tests
poetry run pytest tests/use_cases

# Run specific test file
poetry run pytest tests/use_cases/stories/test_client_registers_issuer_accepts.py
```

**Use Case Test Features:**
- **Fast execution**: Tests run in < 0.1 seconds
- **No external dependencies**: No Docker, Redis, or HTTP servers needed
- **Complete business flows**: Tests verify end-to-end business logic through use cases
- **Isolated state**: Each test gets fresh in-memory storage

**Test Coverage:**
- Registration flows
- Payment channel opening
- Payment processing
- (More tests being migrated from E2E suite)

#### E2E Tests

E2E tests are true end-to-end tests that exercise the full system via HTTP. They require all services (Issuer, Vendor, and their Redis instances) to be running. **You must start services manually before running tests** - tests do not manage Docker Compose lifecycle.

**Prerequisites:**
- Issuer API running on port 8001
- Vendor API running on port 8000
- Redis for issuer on port 6380
- Redis for vendor on port 6379

```sh
# 1. Start required services
source ./envs/issuer.env.sh
docker compose up issuer redis-issuer

source ./envs/vendor.env.sh
docker compose up vendor redis-vendor

# 2. Wait for services to be ready, then run tests
poetry run pytest -m e2e tests/e2e
```

If services are not available, tests will fail with clear error messages indicating which services are missing.

**E2E Test Categories:**

- **Happy Path Tests**: Complete payment flows, channel lifecycle, PayWord flows
- **Business Logic Tests**: Excessive payments, decreasing payments, empty channel closure
- **Security/Tamper Tests**: Invalid signatures, tampered payloads, mismatched public keys, invalid PayWord tokens

The security tests verify that the system correctly rejects:
- Tampered open-channel signatures (signature and PayWord flows)
- Tampered payment signatures
- Mismatched public key claims (issuer and vendor)
- Invalid PayWord tokens (tampered, non-monotonic k, wrong root)

**Test Suite Strategy:**
- **Use case tests** (`tests/use_cases/`): Fast, focused on business logic, no dependencies
- **E2E tests** (`tests/e2e/`): Slower, but verify full system integration through HTTP