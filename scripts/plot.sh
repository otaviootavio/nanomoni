#!/usr/bin/env bash
set -e

poetry run python -m bench_plotter.sweep benchmark_timing.json --title true
