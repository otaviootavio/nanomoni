"""Transform stage for resource steady-state companion figures.

Emits box / ECDF / violin draw tasks from a ``steady_state`` plan job. Plan-side
job construction lives in :mod:`.resource`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from bench_plotter.plotting.windowing import steady_state_samples

from .model import DrawTask, PlotJob, ResultCache
from .series_runs import runs_from_series


def _pool_repeats_by_mode(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trim each repeat individually, then pool samples sharing a mode.

    Warm-up/cool-down must be trimmed *per* repeat (each has its own ramp) before
    concatenation; pooling first would corrupt plateau detection at repeat
    boundaries. Downstream renderers receive already-trimmed values and should
    be called with ``trim=False``.
    """
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for run in runs:
        mode = run.get("interval_mode")
        if mode is None:
            continue
        if mode not in groups:
            order.append(mode)
        groups.setdefault(mode, []).append(run)

    pooled: List[Dict[str, Any]] = []
    for mode in order:
        samples: List[float] = []
        for run in groups[mode]:
            samples.extend(steady_state_samples(run.get("values", [])))
        if len(samples) < 3:
            continue
        pooled.append({"interval_mode": mode, "values": samples})
    return pooled


def transform_steady_state(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build box + ECDF + violin draw tasks from cached resource series."""
    runs = runs_from_series(job.params["series"], cache)
    if not runs:
        return []
    pooled = _pool_repeats_by_mode(runs)
    if not pooled:
        return []
    unit = job.params["unit_label"]
    # Pre-trimmed + pooled; skip the renderers' own steady_state_samples pass.
    return [
        DrawTask(
            fn_name="steady_state_box",
            output_path=job.output_path,
            kwargs={
                "series_list": pooled,
                "title": f"{job.title} (steady-state)",
                "y_axis_label": unit,
                "trim": False,
            },
        ),
        DrawTask(
            fn_name="ecdf",
            output_path=job.params["ecdf_path"],
            kwargs={
                "series_list": pooled,
                "title": f"{job.title} (steady-state, ECDF)",
                "value_label": unit,
                "trim": False,
            },
        ),
        DrawTask(
            fn_name="violin",
            output_path=job.params["violin_path"],
            kwargs={
                "series_list": pooled,
                "title": f"{job.title} (steady-state)",
                "value_label": unit,
                "trim": False,
            },
        ),
    ]
