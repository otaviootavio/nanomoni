#!/usr/bin/env python3
"""Generate payword payment mode plots."""

import sys
import argparse
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bench_plotter.generate_plots.common import clean_plots_directory, auto_detect_intervals
from bench_plotter.plotting import process_payword_dashboard


def main():
    """Main function to generate payword payment mode plots."""
    parser = argparse.ArgumentParser(
        description="Generate payword payment mode plots from dashboard queries and test intervals"
    )
    parser.add_argument(
        "intervals",
        nargs='?',
        help="Path to test intervals JSON file (default: auto-detect in root)"
    )
    parser.add_argument(
        "--output",
        default="plots",
        help="Output directory for generated plots (default: plots)"
    )
    parser.add_argument(
        "--interpol",
        type=int,
        default=100,
        help="Number of interpolation points for time series normalization (default: 100)"
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
    print("Processing payword payment mode")
    
    process_payword_dashboard(
        test_intervals_path=str(intervals_path),
        output_dir=str(output_dir),
        num_points=args.interpol
    )
    
    print(f"Payword plots generated successfully in '{output_dir}' directory!")


if __name__ == "__main__":
    main()
