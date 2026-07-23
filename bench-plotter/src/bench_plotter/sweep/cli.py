"""Command-line entry point for the TPS-sweep plotting pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def positive_int(value: str) -> int:
    """argparse ``type`` validator: a strictly-positive integer.

    ``int(value)`` failures (non-integers) are reported by argparse
    automatically; here we additionally reject zero and negatives so bad
    ``--workers`` values fail fast with a clear CLI error instead of
    propagating into the plotting logic.
    """
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {ivalue}")
    return ivalue


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate per-config timeseries plots and aggregate metric-vs-TPS "
            "charts from a benchmark_timing.json (or legacy list) file"
        )
    )
    parser.add_argument(
        "intervals",
        help="Path to the benchmark timing JSON (e.g. benchmark_timing.json)",
    )
    parser.add_argument(
        "--output",
        default="plots",
        help="Root output directory (default: plots); timestamp subdir is created inside",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=None,
        help="Max parallel draw workers (default: all CPUs)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Render figures serially (debugging)",
    )
    args = parser.parse_args()

    intervals_path = Path(args.intervals)
    if not intervals_path.exists():
        print(f"Error: {intervals_path} not found")
        sys.exit(1)

    print(f"Using timing file: {intervals_path}")
    print(f"Output root: {args.output}")

    from .runner import generate_sweep_plots

    written = generate_sweep_plots(
        timing_path=str(intervals_path),
        output_root=str(args.output),
        workers=args.workers,
        parallel=not args.no_parallel,
    )
    print(f"Sweep complete: {len(written)} plot(s) written")


if __name__ == "__main__":
    main()
