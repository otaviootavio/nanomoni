#!/usr/bin/env bash
set -e

# The Prometheus URL is hardcoded in bench_plotter/settings.py (local default port).
cd "$(dirname "$0")/.."

poetry run python -m bench_plotter.generate_plots "$@"
