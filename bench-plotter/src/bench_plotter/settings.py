"""Configuration for the benchmark plotter.

The Prometheus URL is intentionally hardcoded: the benchmark always runs against a
local Prometheus on the default port. To point at a different instance, edit the
value in ``prometheus_base_url`` below.
"""

from __future__ import annotations

import os


def prometheus_base_url() -> str:
    """Return the (hardcoded) Prometheus base URL for the local benchmark stack."""
    return "http://127.0.0.1:9090"


def web_port() -> int:
    """Return configured web port from environment with sane defaults and bounds."""
    default = 3030
    raw = os.environ.get("WEB_PORT")
    if raw is None:
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default

    # Clamp to valid TCP port range 1-65535
    if val < 1:
        return 1
    if val > 65535:
        return 65535
    return val
