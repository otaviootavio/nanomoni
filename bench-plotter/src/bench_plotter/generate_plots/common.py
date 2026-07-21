#!/usr/bin/env python3
"""Common utilities for generate_plots module."""

import argparse
import sys
from pathlib import Path


def clean_plots_directory(plots_dir: Path) -> None:
    """Clean the plots directory by removing all files."""
    if plots_dir.exists():
        print(f"Cleaning plots directory: {plots_dir}")
        # Recurse into section subdirectories (tps_metrics/, vendor_resources/, ...)
        # so stale plots from removed panels are not left behind.
        for file_path in plots_dir.rglob("*.png"):
            file_path.unlink()
            print(f"Removed: {file_path}")
    else:
        plots_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created plots directory: {plots_dir}")


def auto_detect_intervals(project_root: Path) -> Path:
    """Auto-detect intervals file.

    Searches project_root first (standalone use), then project_root.parent
    (integration use — e.g. when nested inside nanomoni which generates
    benchmark_timing.json one level above).  Matches both *interval*.json
    and *timing*.json patterns.
    """
    patterns = ["*interval*.json", "*timing*.json"]
    search_dirs = [project_root, project_root.parent]

    for search_dir in search_dirs:
        for pattern in patterns:
            candidates = list(search_dir.glob(pattern))
            if candidates:
                intervals_path = candidates[0]
                print(f"Auto-detected intervals: {intervals_path}")
                return intervals_path

    print("Error: No intervals file found")
    print("Expected files like: test_intervals.json or benchmark_timing.json")
    print(f"Searched in: {project_root} and {project_root.parent}")
    sys.exit(1)


def positive_int(value: str) -> int:
    """argparse ``type`` validator: a strictly-positive integer.

    ``int(value)`` failures (non-integers) are reported by argparse
    automatically; here we additionally reject zero and negatives so bad
    ``--interpol`` values fail fast with a clear CLI error instead of
    propagating into the plotting logic.
    """
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {ivalue}")
    return ivalue
