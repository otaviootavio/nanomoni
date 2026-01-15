### NanoMoni (docker compose)

Prereqs:
- Docker + Docker Compose v2 (`docker compose`)

### 1) Start observability (optional)

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

This repo uses `envs/env.*.sh` scripts (they `export ...`) so you can load all required variables into your shell:

```sh
source ./envs/issuer.env.sh
source ./envs/vendor.env.sh
source ./envs/client.env.sh
```

### 4) Build + run the services

Issuer and vendor will start their Redis dependencies via `depends_on`.

```sh
docker compose up -d issuer --build
docker compose up -d vendor --build
docker compose up client --build
```

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
source ./envs/vendor.env.sh
docker compose up -d issuer redis-issuer
docker compose up -d vendor  redis-vendor

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