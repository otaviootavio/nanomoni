#!/usr/bin/env python3
"""Generate paytree payment mode plots."""

import sys
from pathlib import Path

# Add src to path for standalone execution
# (python src/bench_plotter/generate_plots/paytree.py)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bench_plotter.generate_plots.common import run_mode_cli
from bench_plotter.plotting import process_paytree_dashboard


def main() -> None:
    """Main function to generate paytree payment mode plots."""
    run_mode_cli("paytree", process_paytree_dashboard)


if __name__ == "__main__":
    main()
