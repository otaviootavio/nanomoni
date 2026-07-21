"""Fetch time-series ranges from Prometheus HTTP API.

Uses Prometheus's native ``/api/v1/query_range``: each returned point is whatever
Prometheus evaluated at the given ``step`` (no moving average, no Grafana-style transforms).
If you use PromQL like ``rate()`` or ``avg_over_time()``, *that* function defines smoothing —
the app does not add another layer on top.

Matrix payload decoding lives in :mod:`bench_plotter.prometheus_matrix`.
"""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urljoin

import httpx

from bench_plotter.settings import prometheus_base_url


def range_step_for_window(total_seconds: float) -> str:
    """Prometheus ``step`` parameter for query_range (resolution of returned points)."""
    return _step_for_range_seconds(total_seconds)


_SCRAPE_INTERVAL_SECONDS = 15
# Prometheus's query_range API rejects requests whose point count would exceed
# roughly this many points per series.
_MAX_POINTS_PER_SERIES = 11_000


def _step_for_range_seconds(total_seconds: float) -> str:
    """Query at the Prometheus scrape_interval (15s), widening only if needed.

    A step finer than the scrape interval only yields duplicated (stair-stepped)
    points and noisy rate() output, so 15s is the floor. It's also usually the
    ceiling: coarsening the step for large windows is unnecessary noise
    reduction for the minutes-to-hours-long windows this tool queries. But
    Prometheus caps the number of points a query_range call may return, so for
    a window long enough to exceed that cap at 15s, the step is widened just
    enough to stay under it rather than letting the query fail outright.
    """
    if total_seconds <= _SCRAPE_INTERVAL_SECONDS * _MAX_POINTS_PER_SERIES:
        return f"{_SCRAPE_INTERVAL_SECONDS}s"
    step = math.ceil(total_seconds / _MAX_POINTS_PER_SERIES)
    return f"{step}s"


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
        # Parse the body first so descriptive Prometheus JSON errors (returned
        # with 4xx statuses) are preserved instead of being masked by a generic
        # HTTP error. Fall back to raise_for_status only if the body is not JSON.
        try:
            payload = r.json()
        except Exception:
            r.raise_for_status()
            raise
    if payload.get("status") != "success":
        err = payload.get("error") or payload.get("errorType") or "unknown error"
        raise ValueError(f"Prometheus query failed: {err}")
    return payload


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
        try:
            payload = r.json()
        except Exception:
            r.raise_for_status()
            raise
    if payload.get("status") != "success":
        err = payload.get("error") or "unknown error"
        raise ValueError(f"Prometheus label API failed: {err}")
    data = payload.get("data") or []
    return list(data) if isinstance(data, list) else []


async def instant_query(
    *,
    query: str,
    base_url: str | None = None,
    time: float | None = None,
) -> dict[str, Any]:
    """Run an instant query (e.g. scalar check that Prometheus has data).

    When ``time`` is given, the query is evaluated at that Unix timestamp so
    historical benchmark intervals are read from the past rather than from
    Prometheus's current state.
    """
    base = (base_url or prometheus_base_url()).rstrip("/")
    url = urljoin(base + "/", "api/v1/query")
    params = {"query": query}
    if time is not None:
        params["time"] = str(time)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        try:
            payload = r.json()
        except Exception:
            r.raise_for_status()
            raise
    if payload.get("status") != "success":
        err = payload.get("error") or payload.get("errorType") or "unknown error"
        raise ValueError(f"Prometheus instant query failed: {err}")
    return payload
