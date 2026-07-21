"""Decode Prometheus matrix payloads into plot-ready structures.

HTTP transport lives in :mod:`bench_plotter.prometheus_fetch`; this module only
shapes already-fetched JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def matrix_result_is_uninteresting(matrix_result: list[dict[str, Any]]) -> bool:
    """
    True only when there is nothing to plot: no numeric samples at all (empty or all-NaN).

    Constant series (including all-zeros) are kept on purpose: a resource decaying to
    and staying at zero, or a legitimately flat gauge, is exactly what we want to see.
    """
    for item in matrix_result:
        for pair in item.get("values") or []:
            if len(pair) < 2:
                continue
            raw = pair[1]
            if raw == "NaN" or raw is None:
                continue
            try:
                float(raw)
            except (TypeError, ValueError):
                continue
            # Found at least one numeric sample -> there is something to plot.
            return False
    return True


def matrix_to_per_series_charts(
    matrix_result: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One chart per series so each metric keeps its own vertical scale (readable vs one cramped chart)."""
    charts: list[dict[str, Any]] = []
    for item in matrix_result:
        metric = item.get("metric") or {}
        name = metric.get("__name__", "series")
        label_parts = [
            f'{k}="{v}"' for k, v in sorted(metric.items()) if k != "__name__"
        ]
        subtitle = ", ".join(label_parts) if label_parts else "(no labels)"
        values = item.get("values") or []
        labels: list[str] = []
        data: list[float | None] = []
        ts_list: list[float] = []
        for pair in values:
            if len(pair) < 2:
                continue
            ts = float(pair[0])
            ts_list.append(ts)
            raw = pair[1]
            try:
                if raw == "NaN" or raw is None:
                    data.append(None)
                else:
                    data.append(float(raw))
            except (TypeError, ValueError):
                data.append(None)
            labels.append(
                datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
            )
        charts.append(
            {
                "metric_name": name,
                "title": f"{name}",
                "subtitle": subtitle[:200] + ("…" if len(subtitle) > 200 else ""),
                "labels": labels,
                "data": data,
                "timestamps": ts_list,
                "point_count": len(data),
            }
        )
    return charts
