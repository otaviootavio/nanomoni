"""Common utilities shared across plotting modules."""

from __future__ import annotations

import json
from typing import Any, Dict


def load_json_data(file_path: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    with open(file_path, 'r') as f:
        return json.load(f)
