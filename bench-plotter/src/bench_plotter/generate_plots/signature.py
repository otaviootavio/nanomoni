#!/usr/bin/env python3
"""Generate signature payment mode plots."""

import sys
from pathlib import Path

# Add src to path for standalone execution
# (python src/bench_plotter/generate_plots/signature.py)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bench_plotter.generate_plots.common import run_mode_cli
from bench_plotter.plotting import process_signature_dashboard


def main() -> None:
    """Main function to generate signature payment mode plots."""
    run_mode_cli("signature", process_signature_dashboard)


if __name__ == "__main__":
    main()
