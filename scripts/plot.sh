#!/usr/bin/env bash
set -e

PROMETHEUS_PORT="${1:-9090}"
export PROMETHEUS_URL="http://127.0.0.1:${PROMETHEUS_PORT}"

cd "$(dirname "$0")/.."

echo "Using Prometheus at ${PROMETHEUS_URL}"
poetry run python -m bench_plotter.generate_plots "${@:2}"
