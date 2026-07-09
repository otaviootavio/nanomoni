"""Generate plots module organized by payment mode."""

from __future__ import annotations

import argparse

from .common import clean_plots_directory, auto_detect_intervals, positive_int
from .signature import main as main_signature
from .payword import main as main_payword
from .paytree import main as main_paytree


def generate_all_modes(
    intervals_path: str | None = None,
    output_dir: str = "plots",
    num_points: int = 100,
) -> None:
    """
    Generate plots for all payment modes together.

    Args:
        intervals_path: Path to test intervals JSON file (default: auto-detect)
        output_dir: Output directory for generated plots (default: plots)
        num_points: Number of interpolation points (default: 100)
    """
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent

    if intervals_path is None:
        intervals = auto_detect_intervals(project_root)
    else:
        intervals = Path(intervals_path)

    output_dir_path = Path(output_dir)

    if not intervals.exists():
        print(f"Error: {intervals} not found")
        sys.exit(1)

    # Clean plots directory
    clean_plots_directory(output_dir_path)

    # Generate plots for all modes
    print(f"Using test intervals: {intervals}")
    print(f"Output directory: {output_dir}")
    print(f"Using {num_points} interpolation points")
    print("Processing all payment modes together")

    from bench_plotter.plotting import process_all_modes

    process_all_modes(
        test_intervals_path=str(intervals),
        output_dir=str(output_dir),
        num_points=num_points,
    )

    print(f"All plots generated successfully in '{output_dir}' directory!")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate matplotlib plots from dashboard queries and test intervals"
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
        type=positive_int,
        default=100,
        help="Number of interpolation points for time series normalization (default: 100)",
    )
    args = parser.parse_args()
    generate_all_modes(
        intervals_path=args.intervals, output_dir=args.output, num_points=args.interpol
    )


__all__ = [
    "auto_detect_intervals",
    "clean_plots_directory",
    "generate_all_modes",
    "main",
    "main_paytree",
    "main_payword",
    "main_signature",
]
