"""Stage 3: turn fetched payloads into draw tasks.

Pure, in-process, and sequential by design: the work here is pandas/numpy over
tens of points per series, which is far below the threshold where parallelism
would pay for its overhead (the expensive stage is drawing, done in a pool).
Each job expands into one or more :class:`DrawTask`s carrying only plain data,
ready to cross into a draw worker.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bench_plotter.plotting.windowing import calculate_optimal_window_size

from .model import DrawTask, PlotJob, ResultCache
from .series_runs import runs_from_series
from .latency_transform import transform_latency_box, transform_latency_dist
from .distribution_transform import transform_distribution
from .steady_state_transform import transform_steady_state


def _nonzero(values: List[Any]) -> bool:
    return any(v is not None and float(v) != 0 for v in values)


def _series_list(
    runs: List[Dict[str, Any]], window_seconds: Optional[float]
) -> List[Dict[str, Any]]:
    """Build windowed-plot series, dropping all-zero series unless every one is zero."""
    built = []
    for run in runs:
        ts = run["timestamps"]
        ws: Optional[float]
        if window_seconds is not None:
            ws = window_seconds
        else:
            try:
                ws = calculate_optimal_window_size(ts) if ts else None
            except Exception:
                ws = None
        built.append(
            {
                "timestamps": ts,
                "values": run["values"],
                "label": run["interval_mode"],
                "window_seconds": ws,
            }
        )
    if any(_nonzero(s["values"]) for s in built):
        return [s for s in built if _nonzero(s["values"])]
    return built


def _overlay_tasks(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    runs = runs_from_series(job.params["series"], cache)
    if not runs:
        return []
    series_list = _series_list(runs, job.params.get("window_seconds"))
    return [
        DrawTask(
            fn_name="windowed_multi",
            output_path=job.output_path,
            kwargs={
                "series_list": series_list,
                "title": job.title,
                "y_axis_label": job.y_axis_label,
            },
        )
    ]


def _mean_std_tasks(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    runs = runs_from_series(job.params["series"], cache)
    if not runs:
        return []
    return [
        DrawTask(
            fn_name="mean_std",
            output_path=job.output_path,
            kwargs={
                "runs_data": runs,
                "title": job.title,
                "num_points": job.params["num_points"],
                "y_axis_label": job.y_axis_label,
            },
        )
    ]


_DISPATCH = {
    "overlay": _overlay_tasks,
    "mean_std": _mean_std_tasks,
    "steady_state": transform_steady_state,
    "distribution": transform_distribution,
    "latency_box": transform_latency_box,
    "latency_dist": transform_latency_dist,
}


def transform_jobs(jobs: List[PlotJob], cache: ResultCache) -> List[DrawTask]:
    """Expand every job into its draw tasks, in plan order."""
    tasks: List[DrawTask] = []
    for job in jobs:
        handler = _DISPATCH.get(job.kind)
        if handler is None:
            print(f"Unknown job kind '{job.kind}', skipping")
            continue
        tasks.extend(handler(job, cache))
    return tasks
