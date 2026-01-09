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
docker compose up -d issuer vendor
docker compose up client
```

### 4) Stop everything

```sh
docker compose down
```