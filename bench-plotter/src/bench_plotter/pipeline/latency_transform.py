"""Transform stage for steady-state vendor-latency jobs.

Builds draw tasks for the latency box plot and ECDF/violin companions from
cached Prometheus payloads. Plan-side job construction lives in :mod:`.latency`.

When ``REPEATS`` produces several intervals of the same mode, each becomes its
own entry in the plan; this module collapses those to one box / ECDF / violin
per mode (mean of per-repeat quantile stats or bucket CDFs) before drawing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from bench_plotter.prometheus_matrix import matrix_to_per_series_charts
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.plotting.histogram_math import (
    histogram_moments,
    histogram_quantile,
    histogram_to_samples,
)

from .model import DrawTask, PlotJob, ResultCache

_STATS_COLUMNS = ("mode", "mean_ms", "stddev_ms", "p50_ms", "p95_ms")
_BOX_FIELDS = ("whislo", "q1", "med", "q3", "whishi")


def _le_sort_key(le: str) -> float:
    """Sort ``le`` bucket labels numerically, keeping ``+Inf`` last."""
    return float("inf") if le == "+Inf" else float(le)


def _median(samples: List[float]) -> float:
    return sorted(samples)[len(samples) // 2]


def _clamp_nondecreasing_quantiles(qmed: Dict[float, float]) -> None:
    """Clamp quantile values non-decreasing (filter noise can invert them)."""
    ordered = sorted(qmed)
    for prev, cur in zip(ordered, ordered[1:]):
        if qmed[cur] < qmed[prev]:
            qmed[cur] = qmed[prev]


def _group_by_label(
    items: List[Dict[str, Any]], label_key: str = "label"
) -> Tuple[List[Any], Dict[Any, List[Dict[str, Any]]]]:
    """Preserve first-seen label order while grouping items by ``label_key``."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for item in items:
        label = item.get(label_key)
        if label is None:
            continue
        if label not in groups:
            order.append(label)
        groups.setdefault(label, []).append(item)
    return order, groups


def _reduce_box_stats(stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Average box quantile fields across repeats sharing the same mode label."""
    order, groups = _group_by_label(stats)
    reduced: List[Dict[str, Any]] = []
    for label in order:
        group = groups[label]
        if len(group) == 1:
            reduced.append(dict(group[0]))
            continue
        merged: Dict[str, Any] = {"label": label}
        for field in _BOX_FIELDS:
            values = [float(row[field]) for row in group if field in row]
            merged[field] = sum(values) / len(values) if values else 0.0
        # Re-clamp after averaging in case means crossed.
        qmed = {
            0.05: merged["whislo"],
            0.25: merged["q1"],
            0.50: merged["med"],
            0.75: merged["q3"],
            0.95: merged["whishi"],
        }
        _clamp_nondecreasing_quantiles(qmed)
        merged["whislo"] = qmed[0.05]
        merged["q1"] = qmed[0.25]
        merged["med"] = qmed[0.50]
        merged["q3"] = qmed[0.75]
        merged["whishi"] = qmed[0.95]
        reduced.append(merged)
    return reduced


def _reduce_dists(dists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Average bucket CDFs across repeats sharing the same mode label.

    Edges are taken from the first repeat of each mode (Prometheus histogram
    bucket bounds are identical across runs of the same metric). Cum-fractions
    are averaged pointwise on those edges; missing edges on a later repeat are
    skipped for that point. The averaged CDF is re-clamped non-decreasing.
    """
    order, groups = _group_by_label(dists)
    reduced: List[Dict[str, Any]] = []
    for label in order:
        group = groups[label]
        if len(group) == 1:
            reduced.append(dict(group[0]))
            continue
        edges = list(group[0]["edges"])
        n = len(edges)
        means: List[float] = []
        running_max = 0.0
        for i in range(n):
            vals = [
                float(d["cum_fraction"][i])
                for d in group
                if i < len(d.get("edges", []))
                and i < len(d.get("cum_fraction", []))
                and d["edges"][i] == edges[i]
            ]
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            running_max = max(running_max, min(1.0, avg))
            means.append(running_max)
        if means:
            # Keep edges aligned with means if some points were skipped.
            reduced.append(
                {
                    "label": label,
                    "edges": edges[: len(means)],
                    "cum_fraction": means,
                }
            )
    return reduced


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
        _clamp_nondecreasing_quantiles(qmed)

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

    stats = _reduce_box_stats(stats)
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

    dists = _reduce_dists(dists)
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
    stats_rows = _stats_rows(dists)
    if stats_rows:
        tasks.append(
            DrawTask(
                fn_name="stats_table",
                output_path=job.params["stats_path"],
                kwargs={
                    "col_labels": list(_STATS_COLUMNS),
                    "rows": stats_rows,
                    "title": (
                        "Vendor Payment Latency (steady-state, "
                        "estimated from histogram buckets)"
                    ),
                },
            )
        )
    return tasks


def _stats_rows(dists: List[Dict[str, Any]]) -> List[List[Any]]:
    """Per-mode mean/stddev/p50/p95 rows from the bucket distributions.

    All four come from the same bucket CDF so they stay mutually consistent; that
    makes them bucket-resolution estimates, so the p50 here can differ slightly
    from the box plot's, which Prometheus computes server-side.
    """
    rows: List[List[Any]] = []
    for dist in dists:
        edges, cumulative = dist["edges"], dist["cum_fraction"]
        mean, stddev = histogram_moments(edges, cumulative)
        if mean is None:
            continue
        rows.append(
            [
                dist["label"],
                mean,
                stddev,
                histogram_quantile(edges, cumulative, 0.50),
                histogram_quantile(edges, cumulative, 0.95),
            ]
        )
    return rows
