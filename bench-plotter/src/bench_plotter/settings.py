"""Configuration for the benchmark plotter.

The Prometheus and Pyroscope URLs are intentionally hardcoded: the benchmark
always runs against a local stack on the default ports. To point at a
different instance, edit the values below.
"""

from __future__ import annotations


def prometheus_base_url() -> str:
    """Return the (hardcoded) Prometheus base URL for the local benchmark stack."""
    return "http://127.0.0.1:9090"


def pyroscope_base_url() -> str:
    """Return the (hardcoded) Pyroscope base URL for the local benchmark stack."""
    return "http://127.0.0.1:4040"
