"""Shared matrix -> run-dict expansion for transform handlers."""

from __future__ import annotations

from typing import Any, Dict, List

from bench_plotter.prometheus_matrix import matrix_to_per_series_charts

from .model import ResultCache


def runs_from_series(
    series: List[Dict[str, Any]], cache: ResultCache
) -> List[Dict[str, Any]]:
    """Flatten (spec, label) entries into per-Prometheus-series run dicts.

    One entry may yield several matrix series; each becomes its own run tagged
    with the entry's label (mirrors the old fetch_prometheus_data expansion).
    """
    runs: List[Dict[str, Any]] = []
    for entry in series:
        payload = cache.get(entry["spec"])
        if not payload:
            continue
        charts = matrix_to_per_series_charts(payload.get("data", {}).get("result", []))
        for chart in charts:
            runs.append(
                {
                    "timestamps": chart["timestamps"],
                    "values": chart["data"],
                    "interval_mode": entry["label"],
                }
            )
    return runs
