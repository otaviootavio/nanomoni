"""Transform stage for steady-state vendor-latency jobs.

Builds draw tasks for the latency box plot and ECDF/violin companions from
cached Prometheus payloads. Plan-side job construction lives in :mod:`.latency`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from bench_plotter.prometheus_matrix import matrix_to_per_series_charts
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.plotting.histogram_math import histogram_to_samples

from .model import DrawTask, PlotJob, ResultCache


def _le_sort_key(le: str) -> float:
    """Sort ``le`` bucket labels numerically, keeping ``+Inf`` last."""
    return float("inf") if le == "+Inf" else float(le)


def _median(samples: List[float]) -> float:
    return sorted(samples)[len(samples) // 2]


def transform_latency_box(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build the precomputed box-plot draw task from cached quantile queries."""
    stats: List[Dict[str, Any]] = []
    for entry in job.params["entries"]:
        qmed: Dict[float, float] = {}
        for q, spec in entry["quantile_specs"].items():
            payload = cache.get(spec)
            if not payload:
                break
            charts = matrix_to_per_series_charts(
                payload.get("data", {}).get("result", [])
            )
            samples: List[float] = []
            for chart in charts:
                samples = steady_state_samples(chart.get("data", []))
                if samples:
                    break
            if not samples:
                break
            qmed[q] = _median(samples)
        if len(qmed) != len(entry["quantile_specs"]):
            continue

        # A fixed histogram state is monotone in the quantile, so any crossing is
        # filter noise; clamp non-decreasing so bxp never draws an inverted box.
        ordered = sorted(qmed)
        for prev, cur in zip(ordered, ordered[1:]):
            if qmed[cur] < qmed[prev]:
                qmed[cur] = qmed[prev]

        stats.append(
            {
                "label": entry["mode"],
                "whislo": qmed[0.05],
                "q1": qmed[0.25],
                "med": qmed[0.50],
                "q3": qmed[0.75],
                "whishi": qmed[0.95],
            }
        )

    if not stats:
        print("No latency data for box plot")
        return []
    return [
        DrawTask(
            fn_name="precomputed_box",
            output_path=job.output_path,
            kwargs={
                "stats": stats,
                "title": job.title,
                "y_axis_label": "Latency (ms)",
            },
        )
    ]


def transform_latency_dist(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build ECDF + reconstructed-violin draw tasks from cached bucket rates."""
    dists: List[Dict[str, Any]] = []
    for entry in job.params["entries"]:
        payload = cache.get(entry["spec"])
        if not payload:
            continue

        le_value: Dict[str, float] = {}
        for series in payload.get("data", {}).get("result", []):
            le = (series.get("metric") or {}).get("le")
            if le is None:
                continue
            raw = [
                float(p[1])
                for p in series.get("values", [])
                if len(p) >= 2 and p[1] not in (None, "NaN")
            ]
            samples = steady_state_samples(raw)
            if samples:
                le_value[le] = _median(samples)
            elif raw:
                le_value[le] = sum(raw) / len(raw)

        if not le_value:
            continue
        total = le_value.get("+Inf")
        if not total or total <= 0:
            total = max(le_value.values())
        if total <= 0:
            continue

        edges: List[float] = []
        cum_fraction: List[float] = []
        running_max = 0.0  # buckets are cumulative in le; clamp dips from filtering
        for le in sorted(le_value, key=_le_sort_key):
            if le == "+Inf":
                continue
            edges.append(float(le))
            running_max = max(running_max, min(1.0, le_value[le] / total))
            cum_fraction.append(running_max)
        if edges:
            dists.append(
                {"label": entry["mode"], "edges": edges, "cum_fraction": cum_fraction}
            )

    if not dists:
        print("No latency data for distribution plots")
        return []

    tasks = [
        DrawTask(
            fn_name="bucket_ecdf",
            output_path=job.params["ecdf_path"],
            kwargs={
                "dists": dists,
                "title": "Vendor Payment Latency (steady-state, ECDF)",
                "value_label": "Latency (ms)",
            },
        )
    ]
    # Violin reconstructed from bucket counts: keep the tails (trim=False).
    violin_series = [
        {
            "interval_mode": d["label"],
            "values": histogram_to_samples(d["edges"], d["cum_fraction"]),
        }
        for d in dists
    ]
    tasks.append(
        DrawTask(
            fn_name="violin",
            output_path=job.params["violin_path"],
            kwargs={
                "series_list": violin_series,
                "title": "Vendor Payment Latency (steady-state, reconstructed from histogram)",
                "value_label": "Latency (ms)",
                "trim": False,
            },
        )
    )
    return tasks
