#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

: "${BENCHMARK_COUNT_VAR:=1048576}"

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="paytree_child_pair"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
export CLIENT_PAYTREE_MAX_I=$BENCHMARK_COUNT_VAR
# Ensure channel_amount >= (max_i * unit_value) with some headroom for remainder
export CLIENT_CHANNEL_AMOUNT=10000000

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true
