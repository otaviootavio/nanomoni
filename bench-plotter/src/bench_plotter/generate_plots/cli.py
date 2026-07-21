"""Command-line entry point for the plotting pipeline.

Thin argument parsing over :func:`generate_plots_from_benchmark`: resolve the
timing file (explicit or auto-detected), clean the output directory, then run
the pipeline. Kept out of ``__init__`` so importing the package has no CLI side
effects.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import auto_detect_intervals, clean_plots_directory, positive_int


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate matplotlib plots from a benchmark_timing.json file"
    )
    parser.add_argument(
        "intervals",
        nargs="?",
        help="Path to the benchmark timing JSON (default: auto-detect)",
    )
    parser.add_argument(
        "--output", default="plots", help="Output directory (default: plots)"
    )
    parser.add_argument(
        "--interpol",
        type=positive_int,
        default=100,
        help="Interpolation points for mean/std normalization (default: 100)",
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

    project_root = Path(__file__).parent.parent.parent.parent
    intervals_path = (
        Path(args.intervals) if args.intervals else auto_detect_intervals(project_root)
    )
    if not intervals_path.exists():
        print(f"Error: {intervals_path} not found")
        sys.exit(1)

    output_dir = Path(args.output)
    clean_plots_directory(output_dir)

    print(f"Using test intervals: {intervals_path}")
    print(f"Output directory: {output_dir}")

    # Imported lazily so `--help` and arg errors don't pay the matplotlib import.
    from bench_plotter.pipeline import generate_plots_from_benchmark

    generate_plots_from_benchmark(
        test_intervals_path=str(intervals_path),
        output_dir=str(output_dir),
        num_points=args.interpol,
        workers=args.workers,
        parallel=not args.no_parallel,
    )


if __name__ == "__main__":
    main()
