"""Plot generation CLI package.

The single entry point is :func:`bench_plotter.pipeline.generate_plots_from_benchmark`;
``main`` (in :mod:`.cli`) is the thin command-line wrapper. Directory/argument
helpers stay here for reuse and testing.
"""

from __future__ import annotations

from .common import clean_plots_directory, auto_detect_intervals, positive_int
from .cli import main

__all__ = [
    "auto_detect_intervals",
    "clean_plots_directory",
    "positive_int",
    "main",
]
