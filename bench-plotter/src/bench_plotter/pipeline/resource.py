"""Plan stage for non-TPS resource charts (overlay / steady-state)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .model import PlotJob
from .plan_common import legend_and_names, overlay_job, specs_for

# Resource sections + chart-title prefixes that additionally get steady-state
# box/ECDF/violin companions.
_STEADY_STATE_SECTIONS = ("vendor_resources", "client_resources")
_STEADY_STATE_PREFIXES = (
    "Vendor CPU Usage",
    "Vendor Network",
    "Client CPU Usage",
    "Client Network",
)

# The one target whose steady-state rate, divided by the payment rate that drove
# it, is a meaningful per-payment quantity: what the client transmits is the
# payment requests themselves, so KiB/s over payments/s is the average request
# size on the wire.
_PER_PAYMENT_TARGET = ("Client Network (KiB/s)", "Output")


def build_resource_jobs(
    charts: List[Dict[str, Any]],
    intervals: List[Dict[str, Any]],
    output_dir: str,
) -> List[PlotJob]:
    """Jobs for non-TPS resource charts (timeseries overlay).

    When a chart qualifies for steady-state companions, emits a separate
    ``steady_state`` job alongside the overlay (paths first-class in the plan,
    matching :mod:`.latency`'s multi-path pattern).
    """
    jobs: List[PlotJob] = []
    for chart in charts:
        title = chart.get("title", "Chart")
        section = chart.get("section", "general")
        section_dir = Path(output_dir) / section
        for target in chart.get("queries", []):
            expr = target.get("promql")
            if not expr:
                continue
            legend_format = target.get("legend", expr)
            plot_title, stem, y_label = legend_and_names(title, legend_format)
            resolved = specs_for(expr, intervals)
            if not resolved:
                continue
            output_path = str(section_dir / f"{stem}.png")
            series = [{"spec": r["spec"], "label": r["mode"]} for r in resolved]

            jobs.append(
                overlay_job(
                    title=plot_title,
                    output_path=output_path,
                    section=section,
                    series=series,
                    y_axis_label=y_label,
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
            if (title, legend_format) == _PER_PAYMENT_TARGET:
                jobs.extend(
                    _per_payment_jobs(
                        table_path=str(section_dir / f"{stem}_per_payment.png"),
                        bar_path=str(section_dir / f"{stem}_per_payment_bar.png"),
                        section=section,
                        series=series,
                        resolved=resolved,
                        intervals=intervals,
                    )
                )
    return jobs


def _per_payment_jobs(
    *,
    table_path: str,
    bar_path: str,
    section: str,
    series: List[Dict[str, Any]],
    resolved: List[Dict[str, Any]],
    intervals: List[Dict[str, Any]],
) -> List[PlotJob]:
    """The per-payment request-size table + bar chart jobs, or ``[]`` without a
    payment rate.

    Needs each interval's ``tps`` to divide by; callers that build a plan from
    intervals lacking it (the pipeline is usable standalone, not only from a
    sweep) simply get no such jobs rather than a table/chart of blanks.
    """
    tps_by_mode = {
        iv["mode"]: float(iv["tps"])
        for iv in intervals
        if iv.get("mode") and iv.get("tps")
    }
    if not tps_by_mode:
        return []
    specs = [r["spec"] for r in resolved]
    params = {"series": series, "tps_by_mode": tps_by_mode}
    return [
        PlotJob(
            kind="per_payment_table",
            title="Client egress per payment (steady-state mean / target TPS)",
            output_path=table_path,
            section=section,
            specs=specs,
            params=params,
        ),
        PlotJob(
            kind="per_payment_bar",
            title="Client egress per payment by mode (steady-state mean / target TPS)",
            output_path=bar_path,
            section=section,
            specs=specs,
            params=params,
        ),
    ]
