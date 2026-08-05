"""Plan stage for steady-state vendor-latency jobs: box plot + ECDF/violin.

Latency is a Prometheus histogram, so there are no per-observation samples: the
box plot is built from five ``histogram_quantile`` series and the ECDF/violin
from the ``le`` bucket rates. This module owns only the plan-side job
construction; transform-side math lives in :mod:`.latency_transform`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from bench_plotter.metric_queries import LATENCY_BUCKET_METRIC_BY_MODE

from .model import PlotJob, QuerySpec

_QUANTILES = [0.05, 0.25, 0.50, 0.75, 0.95]


def _box_expr(metric: str, q: float) -> str:
    return (
        f"histogram_quantile({q}, sum(rate("
        f'{metric}{{job="vendor-api", status="success"}}[10s])) by (le))'
    )


def _dist_expr(metric: str) -> str:
    return f'sum(rate({metric}{{job="vendor-api", status="success"}}[10s])) by (le)'


def build_latency_jobs(
    intervals: List[Dict[str, Any]],
    output_dir: str,
) -> List[PlotJob]:
    """Emit the latency box + distribution jobs for each known-mode interval.

    Intervals whose mode has no latency bucket metric are skipped by the exact
    ``LATENCY_BUCKET_METRIC_BY_MODE`` lookup below.
    """
    box_entries: List[Dict[str, Any]] = []
    dist_entries: List[Dict[str, Any]] = []
    box_specs: List[QuerySpec] = []
    dist_specs: List[QuerySpec] = []

    for iv in intervals:
        mode = iv.get("mode", "unknown")
        metric = LATENCY_BUCKET_METRIC_BY_MODE.get(mode)
        if metric is None:
            continue
        ts = iv.get("prometheus_timestamps", {}) or {}
        start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        start, end = start_ms / 1000, finish_ms / 1000

        q_specs = {q: QuerySpec(_box_expr(metric, q), start, end) for q in _QUANTILES}
        box_specs += list(q_specs.values())
        box_entries.append({"mode": mode, "quantile_specs": q_specs})

        d_spec = QuerySpec(_dist_expr(metric), start, end)
        dist_specs.append(d_spec)
        dist_entries.append({"mode": mode, "spec": d_spec})

    tps_dir = Path(output_dir) / "tps_metrics"
    jobs: List[PlotJob] = []
    if box_entries:
        jobs.append(
            PlotJob(
                kind="latency_box",
                title="Vendor Payment Latency (steady-state)",
                output_path=str(tps_dir / "vendor_payment_latency_boxplot.png"),
                section="tps_metrics",
                specs=box_specs,
                params={"entries": box_entries},
            )
        )
    if dist_entries:
        jobs.append(
            PlotJob(
                kind="latency_dist",
                title="Vendor Payment Latency",
                output_path=str(tps_dir / "vendor_payment_latency_ecdf.png"),
                section="tps_metrics",
                specs=dist_specs,
                params={
                    "entries": dist_entries,
                    "ecdf_path": str(tps_dir / "vendor_payment_latency_ecdf.png"),
                    "violin_path": str(tps_dir / "vendor_payment_latency_violin.png"),
                    # The box plot's five quantiles say nothing about the mean or
                    # the spread around it; both come off the same buckets these
                    # distribution figures are built from.
                    "stats_path": str(tps_dir / "vendor_payment_latency_stats.png"),
                },
            )
        )
    return jobs
