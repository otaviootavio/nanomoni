"""Aggregate steady-state scalars across a TPS sweep and emit vs-TPS plots.

For each successful run, queries Prometheus over that run's window, trims to
steady-state samples, and reduces to mean scalars. Those points are then
plotted as metric vs TPS (one line per payment mode). Latency uses p50 only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from bench_plotter.metric_queries import LATENCY_BUCKET_METRIC_BY_MODE

# Re-exported (not used directly in this module beyond _series_by_mode) so
# existing internal/test imports of these private names keep working now that
# the implementation lives in the shared mode_style module.
from bench_plotter.mode_style import KNOWN_MODES as _KNOWN_MODES  # noqa: F401
from bench_plotter.mode_style import mode_style as _mode_style  # noqa: F401
from bench_plotter.mode_style import series_by_mode as _series_by_mode
from bench_plotter.pipeline.draw import draw_all
from bench_plotter.pipeline.model import DrawTask
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.prometheus_fetch import query_range
from bench_plotter.prometheus_matrix import matrix_to_per_series_charts

# The saturation sweep's own analysis found that a client asked for more TPS than
# it can sequentially deliver still exits 0 -- e.g. a 1024 target run_benchmark.sh
# only reached ~528 TPS for `signature`. Dividing vendor CPU by the *target* would
# then understate mcpu_per_payment, and by a different factor per mode (whichever
# saturates hardest looks the most "efficient"), distorting the cross-mode
# comparison this chart exists to make. Reusing the same rate + plateau
# extraction the saturation sweep uses keeps both call sites agreeing on what
# "achieved TPS" means.
from bench_plotter.saturation.aggregate import (
    achieved_tps_expr,
    samples_from_payload,
    sustained_rate,
)

# PromQL reused from metric_queries/common.py (Vendor CPU / Vendor Redis CPU).
_VENDOR_CPU_EXPR = (
    "sum(\n"
    "  rate(container_cpu_usage_seconds_total{\n"
    '    job="cadvisor",\n'
    '    container_label_com_docker_compose_service="vendor",\n'
    '    image!=""\n'
    "  }[1m])\n"
    ")"
)
_VENDOR_REDIS_CPU_EXPR = (
    "rate(container_cpu_usage_seconds_total{"
    'job="cadvisor", name="nanomoni-redis-vendor-1", image!=""}[1m])'
)
_CLIENT_NETWORK_OUTPUT_EXPR = (
    "sum(\n"
    "  rate(container_network_transmit_bytes_total{\n"
    '    job="cadvisor",\n'
    '    container_label_com_docker_compose_service="client",\n'
    '    image!=""\n'
    "  }[1m])\n"
    ") / 1024"
)

_MAX_CONCURRENCY = 8


def _latency_quantile_expr(metric: str, q: float) -> str:
    return (
        f"histogram_quantile({q}, sum(rate("
        f'{metric}{{job="vendor-api", status="success"}}[10s])) by (le))'
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
        "client_net_output": _CLIENT_NETWORK_OUTPUT_EXPR,
    }
    if metric:
        queries["latency_p50"] = _latency_quantile_expr(metric, 0.50)
    tps_expr = achieved_tps_expr(str(mode))
    if tps_expr:
        queries["achieved_tps"] = tps_expr

    keys = list(queries.keys())
    payloads = await asyncio.gather(
        *(_fetch_one(queries[k], start, end, sem) for k in keys)
    )
    payload_by_key = dict(zip(keys, payloads))
    series = {
        k: _values_from_payload(p)
        for k, p in payload_by_key.items()
        if k != "achieved_tps"
    }

    vendor_cpu_mean = _steady_mean(series.get("vendor_cpu", []))
    redis_cpu_mean = _steady_mean(series.get("vendor_redis_cpu", []))
    latency_p50 = _steady_mean(series.get("latency_p50", []))
    client_net_output_mean = _steady_mean(series.get("client_net_output", []))

    # Falls back to the target when achieved TPS can't be resolved (e.g. no
    # counter for the mode, or too little data), rather than dropping the point.
    achieved_tps = sustained_rate(
        samples_from_payload(payload_by_key.get("achieved_tps"))
    )
    payments_per_second = achieved_tps if achieved_tps is not None else float(tps)

    mcpu_per_payment = None
    if vendor_cpu_mean is not None and payments_per_second > 0:
        # cores/payment * 1000 = milliCPU per payment
        mcpu_per_payment = (vendor_cpu_mean / payments_per_second) * 1000.0

    client_net_output_kib_per_payment = None
    if client_net_output_mean is not None and payments_per_second > 0:
        # KiB/s / payments/s = KiB per payment
        client_net_output_kib_per_payment = client_net_output_mean / payments_per_second

    return {
        "mode": mode,
        "tps": float(tps),
        "latency_p50": latency_p50,
        "vendor_cpu_mean": vendor_cpu_mean,
        "vendor_redis_cpu_mean": redis_cpu_mean,
        "mcpu_per_payment": mcpu_per_payment,
        "client_net_output_kib_per_payment": client_net_output_kib_per_payment,
    }


async def _collect_scalars(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    results = await asyncio.gather(*(_fetch_run_metrics(run, sem) for run in runs))
    return [r for r in results if r is not None]


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
        (
            "client_network_output_per_payment_vs_tps.png",
            "Client network output per payment vs TPS",
            "Network output (KiB) / payment",
            _series_by_mode(scalars, "client_net_output_kib_per_payment"),
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
