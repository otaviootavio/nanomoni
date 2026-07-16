"""Fetch time-series ranges from Prometheus HTTP API.

Uses Prometheus's native ``/api/v1/query_range``: each returned point is whatever
Prometheus evaluated at the given ``step`` (no moving average, no Grafana-style transforms).
If you use PromQL like ``rate()`` or ``avg_over_time()``, *that* function defines smoothing —
the app does not add another layer on top.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from bench_plotter.settings import prometheus_base_url


def range_step_for_window(total_seconds: float) -> str:
    """Prometheus ``step`` parameter for query_range (resolution of returned points)."""
    return _step_for_range_seconds(total_seconds)


def _step_for_range_seconds(total_seconds: float) -> str:
    """Pick a reasonable scrape step so the chart is not overloaded."""
    if total_seconds <= 300:
        return "5s"
    if total_seconds <= 3600:
        return "15s"
    if total_seconds <= 6 * 3600:
        return "1m"
    if total_seconds <= 24 * 3600:
        return "5m"
    return "15m"


async def query_range(
    *,
    query: str,
    start_unix: float,
    end_unix: float,
    base_url: str | None = None,
    step: str | None = None,
) -> dict[str, Any]:
    base = (base_url or prometheus_base_url()).rstrip("/")
    resolved = step if step else _step_for_range_seconds(end_unix - start_unix)
    params = {
        "query": query,
        "start": str(start_unix),
        "end": str(end_unix),
        "step": resolved,
    }
    url = urljoin(base + "/", "api/v1/query_range")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()
    if payload.get("status") != "success":
        err = payload.get("error") or payload.get("errorType") or "unknown error"
        raise ValueError(f"Prometheus query failed: {err}")
    return payload


def matrix_result_is_uninteresting(matrix_result: list[dict[str, Any]]) -> bool:
    """
    True when there is nothing useful to plot: no numeric samples, or a completely flat series
    (all identical values — includes all zeros and any other constant).
    Only remove if truly constant and not varying at all.
    """
    vals: list[float] = []
    for item in matrix_result:
        for pair in item.get("values") or []:
            if len(pair) < 2:
                continue
            raw = pair[1]
            if raw == "NaN" or raw is None:
                continue
            try:
                vals.append(float(raw))
            except (TypeError, ValueError):
                continue
    if not vals:
        return True
    # Only remove if all values are exactly the same
    if len(set(vals)) == 1:
        return True
    return False


def matrix_to_per_series_charts(
    matrix_result: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One chart per series so each metric keeps its own vertical scale (readable vs one cramped chart)."""
    charts: list[dict[str, Any]] = []
    palette = [
        "#60a5fa",
        "#4ade80",
        "#fbbf24",
        "#fb7185",
        "#c084fc",
        "#2dd4bf",
        "#f472b6",
        "#a3e635",
        "#fb923c",
        "#818cf8",
        "#34d399",
        "#facc15",
        "#e879f9",
        "#38bdf8",
        "#4d7c0f",
        "#be123c",
    ]
    for idx, item in enumerate(matrix_result):
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
                "color": palette[idx % len(palette)],
                "point_count": len(data),
            }
        )
    return charts


async def label_values(
    *,
    label_name: str,
    base_url: str | None = None,
    match: str | None = None,
) -> list[str]:
    """List distinct values for a label (e.g. __name__ for metric names)."""
    base = (base_url or prometheus_base_url()).rstrip("/")
    params: dict[str, str] = {}
    if match:
        params["match[]"] = match
    url = urljoin(base + "/", f"api/v1/label/{label_name}/values")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()
    if payload.get("status") != "success":
        err = payload.get("error") or "unknown error"
        raise ValueError(f"Prometheus label API failed: {err}")
    data = payload.get("data") or []
    return list(data) if isinstance(data, list) else []


async def instant_query(
    *,
    query: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Run an instant query (e.g. scalar check that Prometheus has data)."""
    base = (base_url or prometheus_base_url()).rstrip("/")
    url = urljoin(base + "/", "api/v1/query")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params={"query": query})
        r.raise_for_status()
        payload = r.json()
    if payload.get("status") != "success":
        err = payload.get("error") or payload.get("errorType") or "unknown error"
        raise ValueError(f"Prometheus instant query failed: {err}")
    return payload
