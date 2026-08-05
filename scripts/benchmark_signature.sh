#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

: "${BENCHMARK_COUNT_VAR:=1048576}"

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="signature"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true
