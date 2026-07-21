"""Transform stage for resource steady-state companion figures.

Emits box / ECDF / violin draw tasks from a ``steady_state`` plan job. Plan-side
job construction lives in :mod:`.resource`.
"""

from __future__ import annotations

from typing import List

from .model import DrawTask, PlotJob, ResultCache
from .series_runs import runs_from_series


def transform_steady_state(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build box + ECDF + violin draw tasks from cached resource series."""
    runs = runs_from_series(job.params["series"], cache)
    if not runs:
        return []
    unit = job.params["unit_label"]
    return [
        DrawTask(
            fn_name="steady_state_box",
            output_path=job.output_path,
            kwargs={
                "series_list": runs,
                "title": f"{job.title} (steady-state)",
                "y_axis_label": unit,
            },
        ),
        DrawTask(
            fn_name="ecdf",
            output_path=job.params["ecdf_path"],
            kwargs={
                "series_list": runs,
                "title": f"{job.title} (steady-state, ECDF)",
                "value_label": unit,
            },
        ),
        DrawTask(
            fn_name="violin",
            output_path=job.params["violin_path"],
            kwargs={
                "series_list": runs,
                "title": f"{job.title} (steady-state)",
                "value_label": unit,
            },
        ),
    ]
