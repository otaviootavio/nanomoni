"""Plan stage for non-TPS resource panels (overlay / mean_std / steady-state)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .model import PlotJob
from .plan_common import legend_and_names, overlay_job, specs_for

# Resource sections + panel-title prefixes that additionally get steady-state
# box/ECDF/violin companions. Mirrors the old dashboard_processor gate.
_STEADY_STATE_SECTIONS = ("vendor_resources", "client_resources")
_STEADY_STATE_PREFIXES = (
    "Vendor CPU Usage",
    "Vendor Network",
    "Client CPU Usage",
    "Client Network",
)


def build_resource_jobs(
    panels: List[Dict[str, Any]],
    intervals: List[Dict[str, Any]],
    output_dir: str,
    num_points: int,
    window_seconds: int | None,
    is_single_interval: bool,
) -> List[PlotJob]:
    """Jobs for non-TPS resource panels (timeseries overlay, or mean_std).

    When a single-interval panel qualifies for steady-state companions, emits a
    separate ``steady_state`` job alongside the overlay (paths first-class in the
    plan, matching :mod:`.latency`'s multi-path pattern).
    """
    jobs: List[PlotJob] = []
    for panel in panels:
        title = panel.get("title", "Panel")
        section = panel.get("section", "general")
        section_dir = Path(output_dir) / section
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if not expr:
                continue
            legend_format = target.get("legendFormat", expr)
            plot_title, stem, y_label = legend_and_names(title, legend_format)
            resolved = specs_for(expr, intervals)
            if not resolved:
                continue
            output_path = str(section_dir / f"{stem}.png")
            series = [{"spec": r["spec"], "label": r["mode"]} for r in resolved]

            if is_single_interval:
                jobs.append(
                    overlay_job(
                        title=plot_title,
                        output_path=output_path,
                        section=section,
                        series=series,
                        y_axis_label=y_label,
                        window_seconds=window_seconds,
                    )
                )
                steady = section in _STEADY_STATE_SECTIONS and title.startswith(
                    _STEADY_STATE_PREFIXES
                )
                if steady:
                    jobs.append(
                        PlotJob(
                            kind="steady_state",
                            title=plot_title,
                            output_path=str(section_dir / f"{stem}_boxplot.png"),
                            section=section,
                            specs=[r["spec"] for r in resolved],
                            y_axis_label=y_label,
                            params={
                                "series": series,
                                "ecdf_path": str(section_dir / f"{stem}_ecdf.png"),
                                "violin_path": str(section_dir / f"{stem}_violin.png"),
                                "unit_label": y_label,
                            },
                        )
                    )
            else:
                # Repeated same-mode runs -> mean +/- std band.
                jobs.append(
                    PlotJob(
                        kind="mean_std",
                        title=plot_title,
                        output_path=output_path,
                        section=section,
                        specs=[r["spec"] for r in resolved],
                        y_axis_label=y_label,
                        params={
                            "series": series,
                            "num_points": num_points,
                        },
                    )
                )
    return jobs
