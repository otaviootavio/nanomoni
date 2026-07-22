#!/usr/bin/env bash
set -e

poetry run python -m bench_plotter.generate_plots benchmark_timing.json