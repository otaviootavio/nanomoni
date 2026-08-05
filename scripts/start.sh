#!/bin/bash
set -euo pipefail

docker compose up -d alloy pyroscope cadvisor grafana prometheus

sleep 5
source ./envs/issuer.env.sh && docker compose up issuer -d --build
sleep 5
source ./envs/vendor.env.sh && docker compose up vendor -d --build
