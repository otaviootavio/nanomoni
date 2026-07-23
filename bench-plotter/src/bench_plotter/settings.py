"""Configuration for the benchmark plotter.

The Prometheus URL is intentionally hardcoded: the benchmark always runs against a
local Prometheus on the default port. To point at a different instance, edit the
value in ``prometheus_base_url`` below.
"""

from __future__ import annotations


def prometheus_base_url() -> str:
    """Return the (hardcoded) Prometheus base URL for the local benchmark stack."""
    return "http://127.0.0.1:9090"
