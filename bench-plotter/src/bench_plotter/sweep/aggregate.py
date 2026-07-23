"""Aggregate steady-state scalars across a TPS sweep and emit vs-TPS plots.

For each successful run, queries Prometheus over that run's window, trims to
steady-state samples, and reduces to mean scalars. Those points are then
plotted as metric vs TPS (one line per payment mode). Latency uses p50 only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from bench_plotter.metric_queries import LATENCY_BUCKET_METRIC_BY_MODE
from bench_plotter.pipeline.draw import draw_all
from bench_plotter.pipeline.model import DrawTask
from bench_plotter.plotting.common import PALETTE
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.prometheus_fetch import query_range
from bench_plotter.prometheus_matrix import matrix_to_per_series_charts

# PromQL reused from metric_queries/common.py (Vendor CPU / Vendor Redis CPU).
_VENDOR_CPU_EXPR = (
    "sum(\n"
    "  rate(container_cpu_usage_seconds_total{\n"
    '    job="cadvisor",\n'
    '    container_label_com_docker_compose_service="vendor",\n'
    '    image!=""\n'
    "  }[30s])\n"
    ")"
)
_VENDOR_REDIS_CPU_EXPR = (
    "rate(container_cpu_usage_seconds_total{"
    'job="cadvisor", name="nanomoni-redis-vendor-1", image!=""}[30s])'
)

_MAX_CONCURRENCY = 8

# Stable visual identity per payment mode (sorted-mode index into the palette).
_MODE_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
_KNOWN_MODES = ("paytree", "payword", "signature")


def _mode_style(mode: str) -> Dict[str, str]:
    """Return ``{color, marker}`` for a payment mode (stable across charts)."""
    try:
        idx = _KNOWN_MODES.index(mode)
    except ValueError:
        idx = abs(hash(mode)) % len(PALETTE)
    return {
        "color": PALETTE[idx % len(PALETTE)],
        "marker": _MODE_MARKERS[idx % len(_MODE_MARKERS)],
    }


def _latency_quantile_expr(metric: str, q: float) -> str:
    return (
        f"histogram_quantile({q}, sum(rate("
        f'{metric}{{job="vendor-api", status="success"}}[30s])) by (le))'
    )


def _values_from_payload(payload: Optional[Dict[str, Any]]) -> List[float]:
    """Flatten a Prometheus matrix payload into a single numeric series."""
    if not payload:
        return []
    charts = matrix_to_per_series_charts(payload.get("data", {}).get("result", []))
    if not charts:
        return []
    # Prefer the first (usually only) series; skip None points.
    return [float(v) for v in charts[0].get("data", []) if v is not None]


def _steady_mean(values: List[float]) -> Optional[float]:
    samples = steady_state_samples(values)
    if not samples:
        return None
    return float(np.mean(samples))


async def _fetch_one(
    expr: str,
    start_unix: float,
    end_unix: float,
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    async with sem:
        try:
            return await query_range(
                query=expr, start_unix=start_unix, end_unix=end_unix
            )
        except Exception as exc:  # noqa: BLE001 - recorded as missing scalar
            print(f"  aggregate query failed: {expr[:60]}...: {exc}")
            return None


async def _fetch_run_metrics(
    run: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    """Fetch and reduce all aggregate metrics for one run."""
    mode = run.get("mode")
    tps = run.get("tps")
    if mode is None or tps is None:
        return None
    ts = run.get("prometheus_timestamps", {}) or {}
    start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
    if not start_ms or not finish_ms:
        return None
    start, end = start_ms / 1000.0, finish_ms / 1000.0

    metric = LATENCY_BUCKET_METRIC_BY_MODE.get(mode)
    queries: Dict[str, str] = {
        "vendor_cpu": _VENDOR_CPU_EXPR,
        "vendor_redis_cpu": _VENDOR_REDIS_CPU_EXPR,
    }
    if metric:
        queries["latency_p50"] = _latency_quantile_expr(metric, 0.50)

    keys = list(queries.keys())
    payloads = await asyncio.gather(
        *(_fetch_one(queries[k], start, end, sem) for k in keys)
    )
    series = {k: _values_from_payload(p) for k, p in zip(keys, payloads)}

    vendor_cpu_mean = _steady_mean(series.get("vendor_cpu", []))
    redis_cpu_mean = _steady_mean(series.get("vendor_redis_cpu", []))
    latency_p50 = _steady_mean(series.get("latency_p50", []))

    mcpu_per_payment = None
    if vendor_cpu_mean is not None and float(tps) > 0:
        # cores/payment * 1000 = milliCPU per payment
        mcpu_per_payment = (vendor_cpu_mean / float(tps)) * 1000.0

    return {
        "mode": mode,
        "tps": float(tps),
        "latency_p50": latency_p50,
        "vendor_cpu_mean": vendor_cpu_mean,
        "vendor_redis_cpu_mean": redis_cpu_mean,
        "mcpu_per_payment": mcpu_per_payment,
    }


async def _collect_scalars(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    results = await asyncio.gather(*(_fetch_run_metrics(run, sem) for run in runs))
    return [r for r in results if r is not None]


def _series_by_mode(
    scalars: List[Dict[str, Any]],
    y_key: str,
    label_suffix: str = "",
    linestyle: str = "-",
) -> List[Dict[str, Any]]:
    """Group (tps, y) points by mode for one y-field, with stable mode styling."""
    by_mode: Dict[str, List[Tuple[float, float]]] = {}
    for row in scalars:
        y = row.get(y_key)
        if y is None:
            continue
        mode = row["mode"]
        by_mode.setdefault(mode, []).append((row["tps"], float(y)))

    series: List[Dict[str, Any]] = []
    for mode in sorted(by_mode):
        points = sorted(by_mode[mode], key=lambda p: p[0])
        label = f"{mode}{label_suffix}" if label_suffix else mode
        style = _mode_style(mode)
        series.append(
            {
                "label": label,
                "x_values": [p[0] for p in points],
                "y_values": [p[1] for p in points],
                "color": style["color"],
                "marker": style["marker"],
                "linestyle": linestyle,
            }
        )
    return series


def _latency_series(scalars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One p50 line per mode."""
    return _series_by_mode(scalars, "latency_p50")


def build_aggregate_draw_tasks(
    runs: List[Dict[str, Any]],
    output_dir: str,
) -> List[DrawTask]:
    """Fetch per-run scalars and return DrawTasks for the four vs-TPS charts."""
    if not runs:
        return []

    print(f"Aggregating {len(runs)} run(s) for metric-vs-TPS charts...")
    scalars = asyncio.run(_collect_scalars(runs))
    if not scalars:
        print("No aggregate scalars available; skipping vs-TPS charts")
        return []

    base = Path(output_dir)
    charts = [
        (
            "latency_p50_vs_tps.png",
            "Latency p50 vs TPS",
            "Latency (ms)",
            _latency_series(scalars),
        ),
        (
            "vendor_cpu_vs_tps.png",
            "Vendor CPU (mean, steady-state) vs TPS",
            "CPU (cores)",
            _series_by_mode(scalars, "vendor_cpu_mean"),
        ),
        (
            "vendor_redis_cpu_vs_tps.png",
            "Vendor Redis CPU vs TPS",
            "CPU (cores)",
            _series_by_mode(scalars, "vendor_redis_cpu_mean"),
        ),
        (
            "cpu_seconds_per_payment_vs_tps.png",
            "milliCPU per payment vs TPS",
            "mCPU / payment",
            _series_by_mode(scalars, "mcpu_per_payment"),
        ),
    ]

    tasks: List[DrawTask] = []
    for filename, title, y_label, series in charts:
        if not series:
            print(f"  skipping {filename}: no series")
            continue
        tasks.append(
            DrawTask(
                fn_name="sweep_line",
                output_path=str(base / filename),
                kwargs={
                    "series_list": series,
                    "title": title,
                    "x_axis_label": "TPS",
                    "y_axis_label": y_label,
                },
            )
        )
    return tasks


def generate_aggregate_plots(
    runs: List[Dict[str, Any]],
    output_dir: str,
    workers: int | None = None,
    parallel: bool = True,
) -> List[str]:
    """Build and render the four aggregate vs-TPS charts. Returns written paths."""
    tasks = build_aggregate_draw_tasks(runs, output_dir)
    if not tasks:
        return []
    written, failures = draw_all(tasks, workers=workers, parallel=parallel)
    for f in failures:
        print(f"Aggregate draw failed for {f['output_path']}: {f['error']}")
    return written
