#!/bin/bash
set -euo pipefail
IFS=$'\n\t'


source envs/client.env.sh
export CLIENT_PAYMENT_MODE="signature"

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="payword"

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="paytree"

docker compose up --no-deps --abort-on-container-exit --exit-code-from client client
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true

