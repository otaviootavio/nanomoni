"""Plan stage for TPS/quantile charts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .model import PlotJob
from .naming import (
    extract_payment_mode_from_expr,
    extract_unit_from_title,
    quantile_label,
    sanitize_filename,
)
from .plan_common import legend_and_names, overlay_job, specs_for


def build_tps_jobs(
    tps_by_title: Dict[str, List[Dict[str, Any]]],
    intervals: List[Dict[str, Any]],
    output_dir: str,
) -> List[PlotJob]:
    """Jobs for TPS/quantile charts.

    Single chart per title: each target is its own overlaid figure (series by
    interval mode). Multiple charts per title (one per payment mode): combine
    modes, split by quantile (P99/P95/P50) when present, else one combined plot.
    """
    jobs: List[PlotJob] = []
    for title, charts in tps_by_title.items():
        section = charts[0].get("section", "general")
        section_dir = Path(output_dir) / section
        safe_title = sanitize_filename(title)

        if len(charts) == 1:
            for target in charts[0].get("queries", []):
                expr = target.get("promql")
                if not expr:
                    continue
                legend_format = target.get("legend", expr)
                plot_title, stem, y_label = legend_and_names(title, legend_format)
                resolved = specs_for(expr, intervals)
                if not resolved:
                    continue
                jobs.append(
                    overlay_job(
                        title=plot_title,
                        output_path=str(section_dir / f"{stem}.png"),
                        section=section,
                        series=[
                            {"spec": r["spec"], "label": r["mode"]} for r in resolved
                        ],
                        y_axis_label=y_label,
                    )
                )
            continue

        # Multiple modes share this title: group targets by quantile across charts.
        groups: Dict[str, List[str]] = {}
        has_quantiles = False
        for chart in charts:
            for target in chart.get("queries", []):
                expr = target.get("promql")
                if not expr:
                    continue
                q = quantile_label(target.get("legend", ""))
                key = q if q else "__all__"
                has_quantiles = has_quantiles or q is not None
                groups.setdefault(key, []).append(expr)

        for key, exprs in groups.items():
            series: List[Dict[str, Any]] = []
            for expr in exprs:
                mode = extract_payment_mode_from_expr(expr)
                for r in specs_for(expr, intervals):
                    series.append({"spec": r["spec"], "label": mode})
            if not series:
                continue
            if has_quantiles and key != "__all__":
                out = section_dir / f"{safe_title}_{sanitize_filename(key)}.png"
                plot_title = f"{title} - {key}"
            else:
                out = section_dir / f"{safe_title}.png"
                plot_title = title
            jobs.append(
                overlay_job(
                    title=plot_title,
                    output_path=str(out),
                    section=section,
                    series=series,
                    y_axis_label=extract_unit_from_title(plot_title),
                )
            )
    return jobs
