#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

export BENCHMARK_COUNT_VAR=1048576

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="signature"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true

sleep 120
source envs/client.env.sh
export CLIENT_PAYMENT_MODE="payword"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
export CLIENT_PAYWORD_MAX_K=$BENCHMARK_COUNT_VAR
# Ensure channel_amount >= (max_k * unit_value) with some headroom for remainder
# With unit_value=1 and max_k=500000, we need at least 500000, but use 10000000 for safety
export CLIENT_CHANNEL_AMOUNT=10000000

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true

sleep 120
source envs/client.env.sh
export CLIENT_PAYMENT_MODE="paytree"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
export CLIENT_PAYTREE_MAX_I=$BENCHMARK_COUNT_VAR
# Ensure channel_amount >= (max_i * unit_value) with some headroom for remainder
# With unit_value=1 and max_i=500000, we need at least 500000, but use 10000000 for safety
export CLIENT_CHANNEL_AMOUNT=10000000

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true