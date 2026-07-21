"""Staged, parallel plotting pipeline: timing file -> plan -> fetch -> transform -> draw."""

from .orchestrator import generate_plots_from_benchmark

__all__ = ["generate_plots_from_benchmark"]
