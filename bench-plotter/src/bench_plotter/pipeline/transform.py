"""Stage 3: turn fetched payloads into draw tasks.

Pure, in-process, and sequential by design: the work here is pandas/numpy over
tens of points per series, which is far below the threshold where parallelism
would pay for its overhead (the expensive stage is drawing, done in a pool).
Each job expands into one or more :class:`DrawTask`s carrying only plain data,
ready to cross into a draw worker.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .model import DrawTask, PlotJob, ResultCache
from .series_runs import runs_from_series
from .latency_transform import transform_latency_box, transform_latency_dist
from .per_payment_table_transform import (
    transform_per_payment_bar,
    transform_per_payment_table,
)
from .steady_state_transform import transform_steady_state


def _nonzero(values: List[Any]) -> bool:
    return any(v is not None and float(v) != 0 for v in values)


def _series_list(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build line-plot series, dropping all-zero series unless every one is zero."""
    built = [
        {
            "timestamps": run["timestamps"],
            "values": run["values"],
            "label": run["interval_mode"],
        }
        for run in runs
    ]
    if any(_nonzero(s["values"]) for s in built):
        return [s for s in built if _nonzero(s["values"])]
    return built


def _overlay_tasks(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    runs = runs_from_series(job.params["series"], cache)
    if not runs:
        return []
    series_list = _series_list(runs)
    return [
        DrawTask(
            fn_name="line_multi",
            output_path=job.output_path,
            kwargs={
                "series_list": series_list,
                "title": job.title,
                "y_axis_label": job.y_axis_label,
            },
        )
    ]


_DISPATCH = {
    "overlay": _overlay_tasks,
    "steady_state": transform_steady_state,
    "latency_box": transform_latency_box,
    "latency_dist": transform_latency_dist,
    "per_payment_table": transform_per_payment_table,
    "per_payment_bar": transform_per_payment_bar,
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
