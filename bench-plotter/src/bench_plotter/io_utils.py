"""Matplotlib-free I/O helpers shared by the pipeline."""

from __future__ import annotations

import json
from typing import Any


def load_json_data(file_path: str) -> Any:
    """Load JSON data from file (may be a dict, list, or scalar)."""
    with open(file_path, "r") as f:
        return json.load(f)
