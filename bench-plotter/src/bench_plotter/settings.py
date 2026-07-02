"""Configuration: point this app at the Prometheus started by your benchmark project."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from this package dir up to repo root (wherever .env exists).
_HERE = Path(__file__).resolve()
for _dir in _HERE.parents:
    _env = _dir / ".env"
    if _env.is_file():
        load_dotenv(_env)
        break
else:
    load_dotenv()


def prometheus_base_url() -> str:
    return os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")


def web_port() -> int:
    """Return configured web port from environment with sane defaults and bounds."""
    default = 3030
    raw = os.environ.get('WEB_PORT')
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
