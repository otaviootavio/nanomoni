### NanoMoni (docker compose)

Prereqs:
- Docker + Docker Compose v2 (`docker compose`)

### 1) Start observability (optional)

```sh
docker compose up -d alloy pyroscope cadvisor grafana prometheus
```

### 2) Export runtime environment variables

This repo uses `envs/env.*.sh` scripts (they `export ...`) so you can load all required variables into your shell:

```sh
source ./envs/env.issuer.sh
source ./envs/env.vendor.sh
source ./envs/env.client.sh
```

### 3) Build + run the services

Issuer and vendor will start their Redis dependencies via `depends_on`.

```sh
docker compose up -d issuer vendor --build
docker compose up client
```

### 4) Stop everything

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

#### Integration Tests

Integration tests require Redis to be running. They will automatically skip if Redis is not available.

```sh
# Start Redis (if not already running)
docker run --rm -p 6379:6379 redis:7

# Run integration tests
poetry run pytest tests/integration

# With custom Redis URL
TEST_REDIS_URL=redis://localhost:6379/15 poetry run pytest tests/integration

# With race condition test options
poetry run pytest tests/integration/test_lost_update.py --race-iterations=1000
```

#### E2E Tests

E2E tests require all services to be running. **Tests no longer manage Docker Compose lifecycle** - you must start services manually before running tests.

```sh
# 1. Start required services
source ./envs/env.issuer.sh
source ./envs/env.vendor.sh
docker compose up -d issuer redis-issuer
docker compose up -d vendor  redis-vendor

# 2. Wait for services to be ready, then run tests
poetry run pytest -m e2e tests/e2e
```

If services are not available, tests will fail with clear error messages indicating which services are missing.

#### Stress Tests

Stress tests also require all services to be running.

```sh
# 1. Start required services (same as E2E)
source ./envs/env.issuer.sh
source ./envs/env.vendor.sh
docker compose up -d issuer redis-issuer
docker compose up -d vendor  redis-vendor
# 2. Run stress tests
poetry run pytest -m stress tests/stress
```

#### All Tests

```sh
poetry run pytest
```

Note: E2E and stress tests will fail if services are not already running. Integration tests will skip if Redis is unavailable.