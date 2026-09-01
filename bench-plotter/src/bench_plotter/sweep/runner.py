"""Orchestrate per-config timeseries plots + aggregate vs-TPS charts.

Reads ``benchmark_timing.json`` (object with ``server_run_timestamp`` +
``runs``, or a legacy bare list), groups successful runs by ``(tps,
total_requests)``, writes per-config plots under
``plots/<timestamp>/tps<tps>_req<total>/``, and writes the four aggregate
metric-vs-TPS charts at ``plots/<timestamp>/``.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from bench_plotter.io_utils import load_timing_file as _load_timing
from bench_plotter.pipeline import generate_plots_from_intervals

from bench_plotter.profiling.aggregate import (
    _collect_profiles,
    generate_profile_outputs,
)

from .aggregate import _collect_scalars, generate_aggregate_plots

# Join key shared by the Prometheus-scalar and Pyroscope-profile per-run
# records. ``repeat`` is required so independent repeats of the same
# (mode, tps, total_requests) cell stay as separate rows -- the regressions
# in report/benchmark_methodology.md §3 need those degrees of freedom, not
# the repeat-averaged points the vs-TPS charts consume.
_JOIN_KEYS = ("mode", "tps", "total_requests", "repeat")


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
        # Kept so the pipeline can turn a per-second rate into a per-payment
        # amount (see pipeline/per_payment_table_transform.py).
        "tps": run.get("tps"),
    }


def _join_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record.get(k) for k in _JOIN_KEYS)


def export_raw_run_table(
    runs: List[Dict[str, Any]],
    output_dir: str,
) -> Optional[str]:
    """Merge per-run Prometheus + Pyroscope scalars into ``all_runs.csv``.

    One row per individual run (not repeat-reduced) -- the input shape the
    regressions in report/benchmark_methodology.md §3 need. Both sides already
    produce that granularity via ``_collect_scalars`` / ``_collect_profiles``;
    this only joins them and drops the non-tabular flamebearer ``payload``.

    Both collectors independently compute an ``achieved_tps`` (Prometheus
    plateau rate vs. profile_payments / window length). Keep both under
    distinct names rather than letting one silently overwrite the other.

    Returns the CSV path, or ``None`` when there is nothing to write / the
    fetch failed. Best-effort: a down Prometheus/Pyroscope must not break the
    rest of the sweep (same contract as ``generate_profile_outputs``).
    """
    if not runs:
        return None
    print(f"Exporting per-run metrics table for {len(runs)} run(s)...")
    try:
        scalars = asyncio.run(_collect_scalars(runs))
        profiles = asyncio.run(_collect_profiles(runs))
    except Exception as exc:  # noqa: BLE001 - export is best-effort
        print(f"Per-run metrics export failed: {exc}")
        return None
    if not scalars and not profiles:
        print("No per-run scalars or profiles available; skipping all_runs.csv")
        return None

    by_key: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in scalars:
        by_key[_join_key(row)] = dict(row)
    for row in profiles:
        key = _join_key(row)
        profile_row = {
            k: v for k, v in row.items() if k not in ("payload", "achieved_tps")
        }
        # Keep the profile-side rate under a distinct name so it does not
        # overwrite the Prometheus-plateau ``achieved_tps`` already present
        # from the scalar side (or, when only a profile exists, still land
        # under the same column name for a consistent schema).
        if "achieved_tps" in row:
            profile_row["profile_achieved_tps"] = row["achieved_tps"]
        if key in by_key:
            by_key[key].update(profile_row)
        else:
            by_key[key] = profile_row

    csv_path = Path(output_dir) / "all_runs.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(by_key.values())).to_csv(csv_path, index=False)
    print(f"Wrote per-run metrics table: {csv_path} ({len(by_key)} row(s))")
    return str(csv_path)


def generate_sweep_plots(
    timing_path: str,
    output_root: str = "plots",
    workers: int | None = None,
    parallel: bool = True,
    show_title: bool = True,
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
                    show_title=show_title,
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
            show_title=show_title,
        )
    )
    # Best-effort: a down/unreachable Pyroscope must not fail the rest of the
    # sweep, so generate_profile_outputs already swallows and logs its own
    # errors internally.
    written.extend(
        generate_profile_outputs(
            aggregate_runs,
            output_dir=str(base),
            workers=workers,
            parallel=parallel,
            show_title=show_title,
        )
    )
    # Best-effort: same contract as profiling -- a fetch failure here must
    # not fail the rest of the sweep. CSV path is logged by the exporter;
    # it is not a plot, so it is not appended to ``written``.
    export_raw_run_table(aggregate_runs, output_dir=str(base))
    print(f"Sweep wrote {len(written)} plot(s) under '{base}'")
    return written
