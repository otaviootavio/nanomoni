"""Stage 1: interpret a benchmark run into an in-memory list of plot jobs.

``build_plan`` is pure and side-effect free: it classifies charts and delegates
job construction to domain modules. Nothing here touches Prometheus or
matplotlib -- that is what makes the later stages parallelizable.

Job kinds:

    overlay       -> windowed multi-series line (resource + TPS charts)
    mean_std      -> mean +/- std band across repeated same-mode runs
    steady_state  -> resource box/ECDF/violin companions  (see :mod:`.resource`)
    latency_box   -> steady-state latency box plot        (see :mod:`.latency`)
    latency_dist  -> steady-state latency ECDF + violin    (see :mod:`.latency`)
"""

from __future__ import annotations

from typing import Any, Dict, List

from .model import PlotJob
from .latency import build_latency_jobs
from .resource import build_resource_jobs
from .tps import build_tps_jobs
from .naming import is_tps_chart


def _classify_charts(
    charts: List[Dict[str, Any]],
) -> tuple[
    List[Dict[str, Any]],
    Dict[str, List[Dict[str, Any]]],
]:
    """Split charts into (non-tps, tps-by-title)."""
    non_tps: List[Dict[str, Any]] = []
    tps_by_title: Dict[str, List[Dict[str, Any]]] = {}

    for chart in charts:
        title = chart.get("title", "")
        is_tps = any(
            is_tps_chart(
                title, t.get("legend", t.get("promql", "")), t.get("promql", "")
            )
            for t in chart.get("queries", [])
        )
        if is_tps:
            tps_by_title.setdefault(title, []).append(chart)
        else:
            non_tps.append(chart)

    return non_tps, tps_by_title


def build_plan(
    intervals: List[Dict[str, Any]],
    charts: List[Dict[str, Any]],
    output_dir: str,
    num_points: int = 100,
    window_seconds: int | None = None,
) -> List[PlotJob]:
    """Interpret intervals + charts into the full list of plot jobs.

    ``intervals`` must already be filtered to successful runs. ``is_single_interval``
    follows the old rule: a single interval, or several intervals of *different*
    modes, are drawn individually/overlaid; several intervals of the *same* mode
    become mean/std bands.
    """
    modes = {iv.get("mode") for iv in intervals if iv.get("mode")}
    is_single_interval = len(intervals) == 1 or len(modes) > 1

    non_tps, tps_by_title = _classify_charts(charts)

    jobs: List[PlotJob] = []
    jobs += build_resource_jobs(
        non_tps, intervals, output_dir, num_points, window_seconds, is_single_interval
    )
    jobs += build_tps_jobs(tps_by_title, intervals, output_dir)
    jobs += build_latency_jobs(intervals, output_dir)
    return jobs
