#!/usr/bin/env python3
"""Common utilities for generate_plots module."""

import argparse
import sys
from pathlib import Path
from typing import Callable


def clean_plots_directory(plots_dir: Path) -> None:
    """Clean the plots directory by removing all files."""
    if plots_dir.exists():
        print(f"Cleaning plots directory: {plots_dir}")
        for file_path in plots_dir.glob("*.png"):
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


def run_mode_cli(
    mode_label: str,
    processor: Callable[..., None],
) -> None:
    """Shared CLI driver for the per-mode plot generators.

    Parses args, auto-detects the intervals file, cleans the plots directory,
    and invokes ``processor`` for the given ``mode_label`` (e.g. "signature").

    Args:
        mode_label: Payment mode name used in messages (e.g. "paytree")
        processor: A ``process_<mode>_dashboard`` callable accepting
            ``test_intervals_path``, ``output_dir`` and ``num_points``.
    """
    parser = argparse.ArgumentParser(
        description=(
            f"Generate {mode_label} payment mode plots from dashboard queries "
            "and test intervals"
        )
    )
    parser.add_argument(
        "intervals",
        nargs="?",
        help="Path to test intervals JSON file (default: auto-detect in root)",
    )
    parser.add_argument(
        "--output",
        default="plots",
        help="Output directory for generated plots (default: plots)",
    )
    parser.add_argument(
        "--interpol",
        type=int,
        default=100,
        help="Number of interpolation points for time series normalization (default: 100)",
    )

    args = parser.parse_args()

    # Auto-detect intervals file if not provided
    project_root = Path(__file__).parent.parent.parent.parent

    if args.intervals:
        intervals_path = Path(args.intervals)
    else:
        intervals_path = auto_detect_intervals(project_root)

    output_dir = Path(args.output)

    if not intervals_path.exists():
        print(f"Error: {intervals_path} not found")
        sys.exit(1)

    # Clean plots directory
    clean_plots_directory(output_dir)

    # Generate plots
    print(f"Using test intervals: {intervals_path}")
    print(f"Output directory: {output_dir}")
    print(f"Using {args.interpol} interpolation points")
    print(f"Processing {mode_label} payment mode")

    processor(
        test_intervals_path=str(intervals_path),
        output_dir=str(output_dir),
        num_points=args.interpol,
    )

    print(
        f"{mode_label.capitalize()} plots generated successfully "
        f"in '{output_dir}' directory!"
    )
