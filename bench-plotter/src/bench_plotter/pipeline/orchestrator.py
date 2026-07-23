"""The pipeline core: a list of intervals -> plots, via four stages.

``generate_plots_from_intervals`` drives the pipeline:

    1. plan      - interpret intervals + charts into typed PlotJobs
    2. fetch     - resolve every unique query concurrently (one event loop)
    3. transform - expand jobs into DrawTasks (in-process, cheap)
    4. draw      - render DrawTasks in a process pool (the parallel win)

This module owns none of the stage logic; it only wires the stages together and
reports the outcome, so it stays small and each stage stays independently
testable. The sweep module calls it once per (tps, total_requests) configuration.
"""

from __future__ import annotations

import matplotlib

# Pin the headless backend before any transitive pyplot import; the draw workers
# do the same, but the parent may import plotting code too.
matplotlib.use("Agg")

from typing import Any, Dict, List

from bench_plotter.metric_queries import get_charts_for_modes

from .plan import build_plan
from .fetch import fetch_all
from .transform import transform_jobs
from .draw import draw_all


def generate_plots_from_intervals(
    intervals: List[Dict[str, Any]],
    output_dir: str = "plots",
    workers: int | None = None,
    parallel: bool = True,
) -> List[str]:
    """Generate all plots for a list of successful intervals. Returns PNG paths.

    ``workers`` caps the draw pool (default: all CPUs); ``parallel=False`` draws
    serially for debugging.
    """
    if not intervals:
        print("No successful intervals to plot")
        return []

    modes: set[str] = {m for iv in intervals if (m := iv.get("mode"))}
    charts = get_charts_for_modes(modes)
    if not charts:
        print("No charts found for the modes present in the benchmark")
        return []

    # 1. plan
    jobs = build_plan(intervals, charts, output_dir)
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
