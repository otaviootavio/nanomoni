"""Matplotlib-free I/O helpers shared by the pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def load_json_data(file_path: str) -> Any:
    """Load JSON data from file (may be a dict, list, or scalar)."""
    with open(file_path, "r") as f:
        return json.load(f)


def load_timing_file(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Return ``(server_run_timestamp, runs)`` from a benchmark timing file.

    Accepts the sweep object shape (``{server_run_timestamp, runs}``) or a legacy
    bare list, in which case the timestamp is derived from ``now``. Shared by the
    sweep and saturation runners, which both consume the same file.
    """
    data = load_json_data(path)
    fallback_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if isinstance(data, dict):
        ts = data.get("server_run_timestamp") or fallback_ts
        runs = data.get("runs", [])
        if not isinstance(runs, list):
            runs = []
        return str(ts), [r for r in runs if isinstance(r, dict)]
    if isinstance(data, list):
        return fallback_ts, [r for r in data if isinstance(r, dict)]
    return fallback_ts, []


def load_virtual_clients(path: str) -> Optional[int]:
    """Return the ``virtual_clients`` field from a timing file, if present.

    Sweeps record how many in-process virtual clients drove each run (see
    ``CLIENT_VIRTUAL_CLIENTS`` in ``run_tps_saturation_sweep.sh``); charts read
    it back to label the test configuration instead of leaving the reader to
    guess the concurrency behind the numbers. Legacy timing files (a bare list,
    or an object without this field) have no such record.
    """
    data = load_json_data(path)
    if isinstance(data, dict):
        value = data.get("virtual_clients")
        if isinstance(value, int):
            return value
    return None
