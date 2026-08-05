"""Compare target (expected) TPS against the TPS the vendor actually served.

A single NanoMoni client sends payments in one sequential ``await`` loop, so its
throughput ceiling is ``1 / round_trip_latency``. The client's pacer only ever
*delays* a payment -- it never reports that it fell behind (see
``client/paytree.py``: the ``target > now`` branch is simply skipped once the
loop is late). So a run configured for 4000 TPS that can only manage 1000 exits
successfully and looks identical to one that hit its target.

This module recovers that missing signal after the fact: for each run in a sweep
it reads the vendor's success counter over the run window, reduces it to the
sustained rate, and compares that to what was asked for. The highest target the
client actually kept up with is its saturation point.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from bench_plotter.metric_queries import PAYMENT_COUNTER_METRIC_BY_MODE
from bench_plotter.mode_style import mode_style
from bench_plotter.prometheus_fetch import query_range
from bench_plotter.prometheus_matrix import matrix_to_per_series_charts

# A run counts as having met its target when it served at least this fraction of
# the requested rate. Pacing is best-effort (the sleep is computed from a
# monotonic clock, and Prometheus samples on a 15s scrape), so demanding exactly
# 100% would flag every run as short.
MET_TARGET_RATIO = 0.95

_MAX_CONCURRENCY = 8

# Rate window for the achieved-TPS query, paired with the 1s scrape interval the
# vendor-api job sets in prometheus.yml: 10 samples per window, so a delayed
# scrape cannot turn into a throughput dip or a no-data gap. Keeping the window
# narrow is what allows short runs -- the floor below is a multiple of it.
_RATE_WINDOW = "10s"
_RATE_WINDOW_SECONDS = 10.0

# Query step for the achieved-TPS range query. Overrides the module-level 15s
# floor in prometheus_fetch, which is tuned to the global scrape interval and
# would return only a handful of points across a short run. Deliberately coarser
# than the 1s scrape so the series stays meaningful if the vendor is ever scraped
# less often than prometheus.yml currently specifies.
_QUERY_STEP = "5s"

# A run whose traffic lasts less than this multiple of the rate window cannot be
# measured with rate(): the function divides the counter increase by the whole
# window, so a burst shorter than the window reads low by (span / window) even
# when the client hit its target exactly. Flagged rather than silently reported.
_MIN_SPAN_RATE_WINDOWS = 2.0


def ideal_traffic_span_seconds(
    total_requests: Optional[float],
    expected_tps: float,
) -> Optional[float]:
    """How long a run's traffic should last if the client keeps up.

    ``None`` when the timing entry lacks a request count, in which case the
    rate-window check is skipped rather than guessed at.
    """
    if not total_requests or expected_tps <= 0:
        return None
    return float(total_requests) / expected_tps


def rate_window_too_short(span_seconds: Optional[float]) -> bool:
    """Whether ``rate()`` over ``_RATE_WINDOW`` can measure a run this short."""
    if span_seconds is None:
        return False
    return span_seconds < _MIN_SPAN_RATE_WINDOWS * _RATE_WINDOW_SECONDS


def achieved_tps_expr(mode: str) -> Optional[str]:
    """PromQL for the vendor's served payment rate in ``mode``.

    Returns ``None`` for a mode with no known counter, so a sweep over an
    unrecognized mode name degrades to a missing point rather than a bad query.
    """
    metric = PAYMENT_COUNTER_METRIC_BY_MODE.get(mode)
    if not metric:
        return None
    return f'rate({metric}{{job="vendor-api", status="success"}}[{_RATE_WINDOW}])'


def samples_from_payload(
    payload: Optional[Dict[str, Any]],
) -> List[Tuple[float, float]]:
    """Flatten a Prometheus matrix payload into ``(timestamp, value)`` pairs.

    Timestamps are kept because the plateau is identified by *when* a sample was
    taken, not by how big it is -- see :func:`plateau_samples`.
    """
    if not payload:
        return []
    charts = matrix_to_per_series_charts(payload.get("data", {}).get("result", []))
    if not charts:
        return []
    chart = charts[0]
    timestamps = chart.get("timestamps") or []
    data = chart.get("data") or []
    return [
        (float(t), float(v))
        for t, v in zip(timestamps, data)
        if v is not None and t is not None
    ]


def plateau_samples(
    samples: List[Tuple[float, float]],
    window_seconds: float = _RATE_WINDOW_SECONDS,
) -> List[float]:
    """Keep only the samples whose whole rate() window sits inside the traffic.

    ``rate([W])`` evaluated at ``t`` covers ``(t - W, t]``. While traffic is
    ramping up or draining, part of that window contains no traffic at all, so the
    sample reports a *fraction* of the real rate -- a partial-window artifact, not
    a slow client.

    Magnitude-based trimming cannot separate the two: at a 16 TPS target the last
    ramp sample reads 13.9, which is indistinguishable from a genuine 13%
    shortfall, and averaging it in reported 15.7 for a client that was in fact
    pacing at exactly 16.0. Bound it by time instead. Traffic is observed from the
    first non-zero sample ``t_a`` to the last one ``t_b``; since it may have begun
    anywhere in ``(t_a - W, t_a]`` and ended anywhere in ``(t_b - W, t_b]``, only
    samples in ``[t_a + W, t_b - W]`` are guaranteed fully covered.

    Falls back to every active sample when the run is too short to contain a
    fully-covered window (``rate_window_too_short`` flags that case separately).
    """
    active = [(t, v) for t, v in samples if v > 0]
    if not active:
        return []
    first_ts, last_ts = active[0][0], active[-1][0]
    covered = [
        v
        for t, v in active
        if first_ts + window_seconds <= t <= last_ts - window_seconds
    ]
    return covered or [v for _, v in active]


def sustained_rate(samples: List[Tuple[float, float]]) -> Optional[float]:
    """Reduce a rate series to the throughput the run actually held.

    Averages the fully-covered plateau. No magnitude band is applied on top: the
    coverage rule has already removed the partial-window samples, and clipping
    what remains would also hide genuine mid-run variation (a vendor stall, or a
    client progressively falling behind), which is exactly what this benchmark
    exists to surface.
    """
    plateau = plateau_samples(samples)
    if not plateau:
        return None
    return float(np.mean(plateau))


async def _fetch_run(
    run: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    """Resolve one run's expected vs achieved TPS."""
    mode, tps = run.get("mode"), run.get("tps")
    if mode is None or tps is None:
        return None
    ts = run.get("prometheus_timestamps", {}) or {}
    start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
    if not start_ms or not finish_ms:
        return None
    expr = achieved_tps_expr(str(mode))
    if expr is None:
        print(f"  no known payment counter for mode {mode!r}; skipping")
        return None

    async with sem:
        try:
            payload = await query_range(
                query=expr,
                start_unix=start_ms / 1000.0,
                end_unix=finish_ms / 1000.0,
                step=_QUERY_STEP,
            )
        except Exception as exc:  # noqa: BLE001 - recorded as a missing point
            print(f"  saturation query failed for {mode}@{tps}: {exc}")
            payload = None

    expected = float(tps)
    achieved = sustained_rate(samples_from_payload(payload))
    ratio = None if achieved is None or expected <= 0 else achieved / expected
    span = ideal_traffic_span_seconds(run.get("total_requests"), expected)
    unmeasurable = rate_window_too_short(span)
    if unmeasurable:
        print(
            f"  WARNING {mode}@{tps}: only ~{span:.0f}s of traffic, shorter than "
            f"{_MIN_SPAN_RATE_WINDOWS:.0f}x the {_RATE_WINDOW} rate window -- "
            "achieved TPS is understated; raise RUN_DURATION_SEC"
        )
    return {
        "mode": str(mode),
        "expected_tps": expected,
        "achieved_tps": achieved,
        "ratio": ratio,
        # A short run reads low by construction, so it cannot be called a
        # shortfall -- that verdict would be an artifact of the rate window.
        "met_target": (
            ratio is not None and ratio >= MET_TARGET_RATIO and not unmeasurable
        ),
        "rate_window_too_short": unmeasurable,
        "status": run.get("status"),
    }


def collect_points(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve expected vs achieved TPS for every run, in sweep order."""

    async def _run() -> List[Optional[Dict[str, Any]]]:
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        return list(await asyncio.gather(*(_fetch_run(r, sem) for r in runs)))

    points = [p for p in asyncio.run(_run()) if p is not None]
    points.sort(key=lambda p: (p["mode"], p["expected_tps"]))
    return points


def saturation_tps(points: List[Dict[str, Any]], mode: str) -> Optional[float]:
    """Highest target ``mode`` sustained: the last on-target point before falling short.

    Stops at the first shortfall rather than taking the maximum on-target point
    overall, so one anomalous high-TPS run that happens to land inside tolerance
    cannot report a ceiling above a target the client already failed.
    """
    ordered = sorted(
        (p for p in points if p["mode"] == mode), key=lambda p: p["expected_tps"]
    )
    ceiling: Optional[float] = None
    for point in ordered:
        if not point["met_target"]:
            break
        ceiling = point["expected_tps"]
    return ceiling


def build_delta_table(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pivot points into a target-TPS x protocol grid of real (achieved) TPS.

    Returns ``{"tps_values": [...], "modes": [...], "achieved": [[...]]}`` where
    ``achieved[row][col]`` pairs with ``tps_values[row]`` and ``modes[col]``, and
    is ``None`` where that combination has no measurement.
    """
    modes = sorted({p["mode"] for p in points})
    tps_values = sorted({p["expected_tps"] for p in points})
    by_cell = {(p["mode"], p["expected_tps"]): p for p in points}

    achieved_grid: List[List[Optional[float]]] = []
    for tps in tps_values:
        row: List[Optional[float]] = []
        for mode in modes:
            point = by_cell.get((mode, tps))
            row.append(point["achieved_tps"] if point else None)
        achieved_grid.append(row)

    return {"tps_values": tps_values, "modes": modes, "achieved": achieved_grid}


def build_series(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One achieved-TPS line per mode.

    The ``y = x`` reference line is drawn by
    ``plotting.sweep_renderers.create_identity_comparison_plot``, which owns the
    axis range it has to span -- so it is deliberately not a series here.
    """
    series: List[Dict[str, Any]] = []
    for mode in sorted({p["mode"] for p in points}):
        drawable = [
            p for p in points if p["mode"] == mode and p["achieved_tps"] is not None
        ]
        if not drawable:
            continue
        style = mode_style(mode)
        series.append(
            {
                "label": f"{mode} (real)",
                "x_values": [p["expected_tps"] for p in drawable],
                "y_values": [p["achieved_tps"] for p in drawable],
                "color": style["color"],
                "marker": style["marker"],
                "linestyle": "-",
            }
        )
    return series


def summarize(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the JSON summary: every point plus the per-mode saturation TPS."""
    modes = sorted({p["mode"] for p in points})
    return {
        "met_target_ratio": MET_TARGET_RATIO,
        "rate_window": _RATE_WINDOW,
        "saturation_tps_by_mode": {m: saturation_tps(points, m) for m in modes},
        "points": points,
    }
