"""Orchestrate per-config timeseries plots + aggregate vs-TPS charts.

Reads ``benchmark_timming.json`` (object with ``server_run_timestamp`` +
``runs``, or a legacy bare list), groups successful runs by ``(tps,
total_requests)``, writes per-config plots under
``plots/<timestamp>/tps<tps>_req<total>/``, and writes the four aggregate
metric-vs-TPS charts at ``plots/<timestamp>/``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from bench_plotter.io_utils import load_json_data
from bench_plotter.pipeline import generate_plots_from_intervals

from .aggregate import generate_aggregate_plots


def _load_timing(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Return ``(server_run_timestamp, runs)`` from a timing file.

    Accepts the sweep object shape or a legacy bare list (timestamp then
    derived from ``now``).
    """
    data = load_json_data(path)
    if isinstance(data, dict):
        ts = data.get("server_run_timestamp") or datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        runs = data.get("runs", [])
        if not isinstance(runs, list):
            runs = []
        return str(ts), [r for r in runs if isinstance(r, dict)]
    if isinstance(data, list):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return ts, [r for r in data if isinstance(r, dict)]
    return datetime.now().strftime("%Y%m%d_%H%M%S"), []


def _successful(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in runs if r.get("status") in (None, "success")]


def group_runs_by_config(
    runs: List[Dict[str, Any]],
) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
    """Group runs by ``(tps, total_requests)``, preserving insertion order."""
    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
    for run in runs:
        tps = run.get("tps")
        total = run.get("total_requests")
        if tps is None or total is None:
            continue
        groups[(int(tps), int(total))].append(run)
    return dict(groups)


def config_dirname(tps: int, total_requests: int) -> str:
    """Folder name for one sweep configuration."""
    return f"tps{tps}_req{total_requests}"


def _interval_for_pipeline(run: Dict[str, Any]) -> Dict[str, Any]:
    """Strip sweep-only fields down to what the per-run pipeline expects."""
    return {
        "mode": run.get("mode"),
        "status": run.get("status", "success"),
        "prometheus_timestamps": run.get("prometheus_timestamps", {}),
    }


def generate_sweep_plots(
    timing_path: str,
    output_root: str = "plots",
    workers: int | None = None,
    parallel: bool = True,
) -> List[str]:
    """Generate per-config + aggregate plots for a TPS sweep. Returns PNG paths."""
    server_ts, all_runs = _load_timing(timing_path)
    runs = _successful(all_runs)
    if not runs:
        print("No successful runs to plot")
        return []

    base = Path(output_root) / server_ts
    base.mkdir(parents=True, exist_ok=True)
    print(f"Sweep output directory: {base}")

    written: List[str] = []
    groups = group_runs_by_config(runs)
    if not groups:
        print(
            "No runs with tps/total_requests; skipping per-config plots "
            "(will still attempt aggregate if fields are present on runs)"
        )
    else:
        for (tps, total), group in sorted(groups.items()):
            cfg_dir = base / config_dirname(tps, total)
            intervals = [_interval_for_pipeline(r) for r in group]
            print(
                f"=== Config tps={tps} req={total}: "
                f"{len(intervals)} mode(s) -> {cfg_dir} ==="
            )
            written.extend(
                generate_plots_from_intervals(
                    intervals,
                    output_dir=str(cfg_dir),
                    workers=workers,
                    parallel=parallel,
                )
            )

    # Aggregate charts need tps on each run; filter those that have it.
    aggregate_runs = [r for r in runs if r.get("tps") is not None]
    written.extend(
        generate_aggregate_plots(
            aggregate_runs,
            output_dir=str(base),
            workers=workers,
            parallel=parallel,
        )
    )
    print(f"Sweep wrote {len(written)} plot(s) under '{base}'")
    return written
