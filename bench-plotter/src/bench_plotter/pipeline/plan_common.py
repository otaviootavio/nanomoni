"""Shared helpers for plan-stage job construction.

Used by :mod:`.resource` and :mod:`.tps` so those modules do not import from
:mod:`.plan` (which would cycle through the aggregator).
"""

from __future__ import annotations

from typing import Any, Dict, List

from bench_plotter.plotting.query_utils import sanitize_query

from .model import PlotJob, QuerySpec
from .naming import extract_unit_from_title, sanitize_filename


def specs_for(expr: str, intervals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One range QuerySpec per interval, paired with that interval's mode.

    Returns ``[{"spec": QuerySpec, "mode": <interval mode>}]``. The expr is
    sanitized here so the fetch stage dedups on the canonical form.
    """
    out: List[Dict[str, Any]] = []
    sane = sanitize_query(expr)
    for idx, iv in enumerate(intervals):
        ts = iv.get("prometheus_timestamps", {}) or {}
        start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        out.append(
            {
                "spec": QuerySpec(sane, start_ms / 1000, finish_ms / 1000),
                "mode": iv.get("mode", f"interval_{idx + 1}"),
            }
        )
    return out


def overlay_job(
    *,
    title: str,
    output_path: str,
    section: str,
    series: List[Dict[str, Any]],
    y_axis_label: str,
    window_seconds: int | None,
) -> PlotJob:
    """Build an ``overlay`` job from resolved (spec, label) series entries."""
    return PlotJob(
        kind="overlay",
        title=title,
        output_path=output_path,
        section=section,
        specs=[s["spec"] for s in series],
        y_axis_label=y_axis_label,
        params={
            "series": series,  # [{"spec": QuerySpec, "label": str}]
            "window_seconds": window_seconds,
            "unit_label": y_axis_label,
        },
    )


def legend_and_names(panel_title: str, legend_format: str) -> tuple[str, str, str]:
    """Resolve (plot_title, safe_stem_with_suffix, y_axis_label) for one target.

    Reproduces the ``__auto`` handling: an ``__auto`` legend collapses to the
    panel title with no filename suffix; otherwise the legend is appended.
    """
    safe_title = sanitize_filename(panel_title)
    if legend_format == "__auto":
        plot_title = panel_title
        stem = safe_title
    else:
        plot_title = f"{panel_title} - {legend_format}"
        stem = f"{safe_title}_{sanitize_filename(legend_format)}"
    return plot_title, stem, extract_unit_from_title(plot_title)
