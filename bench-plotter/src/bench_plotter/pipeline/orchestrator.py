"""The single entry point: benchmark timing file -> plots, via four stages.

``generate_plots_from_benchmark`` reads ``benchmark_timing.json`` into an
in-memory plan and drives the pipeline:

    1. plan      - interpret intervals + panels into typed PlotJobs
    2. fetch     - resolve every unique query concurrently (one event loop)
    3. transform - expand jobs into DrawTasks (in-process, cheap)
    4. draw      - render DrawTasks in a process pool (the parallel win)

This module owns none of the stage logic; it only wires the stages together and
reports the outcome, so it stays small and each stage stays independently
testable.
"""

from __future__ import annotations

import matplotlib

# Pin the headless backend before any transitive pyplot import; the draw workers
# do the same, but the parent may import plotting code too.
matplotlib.use("Agg")

from typing import Any, Dict, List

from bench_plotter.dashboard_queries import get_dashboard_panels_for_modes
from bench_plotter.io_utils import load_json_data

from .plan import build_plan
from .fetch import fetch_all
from .transform import transform_jobs
from .draw import draw_all


def _load_successful_intervals(path: str) -> List[Dict[str, Any]]:
    """Load intervals, dropping any the benchmark recorded as non-success.

    Intervals without a ``status`` field are kept (backward compatible).
    """
    data = load_json_data(path)
    if not isinstance(data, list):
        return []
    kept = [
        iv
        for iv in data
        if isinstance(iv, dict) and iv.get("status") in (None, "success")
    ]
    skipped = len(data) - len(kept)
    if skipped:
        print(f"Skipping {skipped} interval(s) with status != 'success'")
    return kept


def generate_plots_from_benchmark(
    test_intervals_path: str,
    output_dir: str = "plots",
    num_points: int = 100,
    window_seconds: int | None = None,
    workers: int | None = None,
    parallel: bool = True,
) -> List[str]:
    """Generate all plots for a benchmark run. Returns the written PNG paths.

    ``workers`` caps the draw pool (default: all CPUs); ``parallel=False`` draws
    serially for debugging.
    """
    intervals = _load_successful_intervals(test_intervals_path)
    if not intervals:
        print("No successful intervals to plot")
        return []

    modes: set[str] = {
        m for iv in intervals if (m := iv.get("mode"))
    }
    panels = get_dashboard_panels_for_modes(modes)
    if not panels:
        print("No panels found for the modes present in the benchmark")
        return []

    # 1. plan
    jobs = build_plan(intervals, panels, output_dir, num_points, window_seconds)
    print(f"Planned {len(jobs)} plot job(s) for modes: {sorted(modes)}")

    # 2. fetch (concurrent, de-duplicated)
    cache, fetch_failures = fetch_all(jobs)

    # 3. transform (in-process)
    tasks = transform_jobs(jobs, cache)
    print(f"Prepared {len(tasks)} figure(s)")

    # 4. draw (process pool)
    written, draw_failures = draw_all(tasks, workers=workers, parallel=parallel)

    _report_failures(fetch_failures, draw_failures)
    print(f"Wrote {len(written)} plot(s) to '{output_dir}'")
    return written


def _report_failures(
    fetch_failures: List[Dict[str, Any]], draw_failures: List[Dict[str, Any]]
) -> None:
    if not fetch_failures and not draw_failures:
        print("\n✅ All data fetched and all figures rendered.")
        return
    if fetch_failures:
        print(f"\n⚠️  {len(fetch_failures)} query(ies) failed:")
        for f in fetch_failures:
            print(f"  • {f['query'][:70]} [{f['interval']}]: {f['error']}")
    if draw_failures:
        print(f"\n⚠️  {len(draw_failures)} figure(s) failed to render:")
        for f in draw_failures:
            print(f"  • {f['output_path']}: {f['error']}")
