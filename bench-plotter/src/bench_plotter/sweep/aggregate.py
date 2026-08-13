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
# PromQL reused from metric_queries/common.py ("Vendor Redis Memory Usage (MiB)").
_VENDOR_REDIS_MEMORY_EXPR = (
    "container_memory_working_set_bytes{"
    'container_label_com_docker_compose_service="redis-vendor", image!=""'
    "} / 1024 / 1024"
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
_BYTES_PER_MIB = 1024.0 * 1024.0

# Drain window to assume for runs written before ``drain_sec`` was recorded.
# Checked against the 20260806 sweep: 15% of the window reproduces the recorded
# 180s drain on every run of every mode, and stays inside the tightest
# drain-to-window ratio in that sweep (15.8%, signature at 4096 TPS, whose run
# overran its target duration and so stretched the window around a fixed drain).
_DEFAULT_DRAIN_FRACTION = 0.15


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


def _points_from_payload(
    payload: Optional[Dict[str, Any]],
) -> List[Tuple[float, float]]:
    """Flatten a matrix payload into (timestamp, value), keeping the clock.

    ``_values_from_payload`` drops timestamps, which is fine for metrics reduced
    to a mean. Reductions that need to know *where* in the run a sample fell
    (see ``_settled_value``) use this instead.
    """
    if not payload:
        return []
    charts = matrix_to_per_series_charts(payload.get("data", {}).get("result", []))
    if not charts:
        return []
    chart = charts[0]
    stamps = chart.get("timestamps") or []
    data = chart.get("data") or []
    return [
        (float(t), float(v))
        for t, v in zip(stamps, data)
        if t is not None and v is not None
    ]


def _settled_value(
    points: List[Tuple[float, float]],
    end_unix: float,
    drain_sec: Optional[float],
) -> Optional[float]:
    """Median of the drain window: what the vendor is left holding after a run.

    Deliberately not the peak. The peak assumes memory only ever climbs inside
    the window, and that is false for any mode with a teardown transient:
    ``paytree_first_opt`` settlement issues one huge node-store read per channel
    (see the vendor's ``_rebuild_paytree_proof_for_settlement``), which briefly
    pushes Redis's RSS far above the dataset it actually retains. That transient
    is shorter than a cadvisor scrape, so ``max`` captures it only by luck --
    turning a flat ~423 bytes/payment into a 421..856 sawtooth across a sweep.

    The median (rather than the last sample, or a mean) is what makes this
    robust: the drain holds tens of samples on a flat plateau, so a few
    still-elevated ones at its start cannot move the answer.

    ``drain_sec`` is the harness's post-client idle gap, recorded per run by
    run_benchmark.sh. Runs written before that field existed fall back to a
    fraction of the window.
    """
    if not points:
        return None
    window = end_unix - points[0][0]
    if drain_sec is None or drain_sec <= 0:
        drain_sec = window * _DEFAULT_DRAIN_FRACTION
    tail = [v for t, v in points if t >= end_unix - drain_sec]
    if not tail:
        tail = [points[-1][1]]
    return float(np.median(tail))


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
        "vendor_redis_memory": _VENDOR_REDIS_MEMORY_EXPR,
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

    # container_memory_working_set_bytes / 1024 / 1024 (_VENDOR_REDIS_MEMORY_EXPR
    # above) is MiB (binary), not MB (decimal) -- named accordingly throughout.
    # Baseline is the floor over the whole window (the pre-run level the harness
    # flushed Redis down to); settled is the drain-window plateau. Taking the
    # floor over the *whole* window, tail included, is also what keeps the delta
    # from ever going negative.
    mem_points = _points_from_payload(payload_by_key.get("vendor_redis_memory"))
    redis_mem_baseline = min((v for _, v in mem_points), default=None)
    redis_mem_settled = _settled_value(mem_points, end, run.get("drain_sec"))
    redis_mem_delta_mib = (
        redis_mem_settled - redis_mem_baseline
        if redis_mem_baseline is not None and redis_mem_settled is not None
        else None
    )

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

    total_requests = run.get("total_requests")
    redis_mem_delta_bytes_per_payment = None
    if redis_mem_delta_mib is not None and total_requests:
        # MiB delta over this run's whole window / this run's payment count =
        # bytes written to Redis per payment -- readable at this magnitude,
        # unlike the MiB delta itself (a tiny fraction of a MiB per payment).
        redis_mem_delta_bytes_per_payment = (
            redis_mem_delta_mib * _BYTES_PER_MIB / total_requests
        )

    return {
        "mode": mode,
        "tps": float(tps),
        "total_requests": run.get("total_requests"),
        "latency_p50": latency_p50,
        "vendor_cpu_mean": vendor_cpu_mean,
        "vendor_redis_cpu_mean": redis_cpu_mean,
        "mcpu_per_payment": mcpu_per_payment,
        "client_net_output_kib_per_payment": client_net_output_kib_per_payment,
        "vendor_redis_memory_baseline_mib": redis_mem_baseline,
        "vendor_redis_memory_settled_mib": redis_mem_settled,
        "vendor_redis_memory_delta_mib": redis_mem_delta_mib,
        "vendor_redis_memory_delta_bytes_per_payment": redis_mem_delta_bytes_per_payment,
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
    """Fetch per-run scalars and return DrawTasks for the vs-TPS charts plus
    the per-TPS Redis memory baseline/peak/delta table."""
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

    # Redis memory delta vs total payments -- keyed by total payments rather
    # than TPS for the same reason as the table below: it is the payment
    # count, not the rate it arrived at, that grows Redis's footprint.
    # Complements the exact baseline/settled/delta table with the growth trend at a
    # glance. Deliberately not labelled "(leak)": whether a climbing line is a
    # leak or expected growth is a judgment call for whoever reads the chart,
    # not something this label should presuppose.
    redis_delta_series = _series_by_mode(
        scalars, "vendor_redis_memory_delta_mib", x_key="total_requests"
    )
    if redis_delta_series:
        tasks.append(
            DrawTask(
                fn_name="sweep_line",
                output_path=str(base / "redis_memory_delta_vs_payments.png"),
                kwargs={
                    "series_list": redis_delta_series,
                    "title": "Vendor Redis memory delta vs total payments",
                    "x_axis_label": "Total payments",
                    "y_axis_label": "Redis memory delta (MiB)",
                    "x_log_base": 2,
                    # A real log axis, not the rank-remap: the sweep's total
                    # payment counts (960, 1920, ...) are not literally 2^0,
                    # 2^1, ... themselves (only the TPS driving them doubles),
                    # so rank-remapping them onto 0, 1, 2, ... mislabels the
                    # first point as "2^0 payments" -- i.e. a single payment --
                    # when the smallest run is actually several hundred. A true
                    # log axis places each point at its real exponent instead.
                    "x_true_log": True,
                    # Deltas span multiple orders of magnitude across modes (well
                    # under 1 MiB up to over 1 GiB), so a linear axis squashes
                    # every mode but the leakiest flat against zero. Log2 keeps
                    # every mode's line visible; ticks are still labelled by raw
                    # MiB (see sweep_renderers._log_value_formatter), so the
                    # numbers read directly against
                    # vendor_redis_memory_delta_vs_payments_table.png instead of
                    # the exponent that made this look negative before.
                    "y_log_base": 2,
                },
            )
        )

    # Same delta, normalized to bytes/payment, tracking how that per-payment
    # cost trends as the sweep's payment count grows -- a flat line is a
    # constant per-payment footprint; a climbing one means each payment gets
    # more expensive to store as the run goes on (the merkle-node-leak
    # signature). x is a real log axis (not the rank-remap above) because the
    # request specifically asked to see total payments *as* a log-scaled
    # quantity here, not just evenly spaced.
    redis_bytes_per_payment_series = _series_by_mode(
        scalars,
        "vendor_redis_memory_delta_bytes_per_payment",
        x_key="total_requests",
    )
    if redis_bytes_per_payment_series:
        tasks.append(
            DrawTask(
                fn_name="sweep_line",
                output_path=str(
                    base
                    / "vendor_redis_memory_delta_bytes_per_payments_vs_total_payments.png"
                ),
                kwargs={
                    "series_list": redis_bytes_per_payment_series,
                    "title": "Vendor Redis memory delta per payment vs total payments",
                    "x_axis_label": "Total payments",
                    "y_axis_label": "Redis memory delta (bytes / payment)",
                    "x_log_base": 2,
                    "x_true_log": True,
                },
            )
        )

    # Per-TPS baseline/settled/delta table, one row per mode, written alongside
    # that config's memory-vs-time chart (same folder the per-config pipeline
    # already writes "Vendor Redis Memory Usage (MiB)" to).
    by_config: Dict[Tuple[float, Any], List[Dict[str, Any]]] = {}
    for row in scalars:
        if row.get("vendor_redis_memory_delta_mib") is None:
            continue
        by_config.setdefault((row["tps"], row.get("total_requests")), []).append(row)
    for (tps, total_requests), rows in sorted(
        by_config.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)
    ):
        total = int(total_requests or 0)
        sorted_rows = sorted(rows, key=lambda r: r["mode"])
        table_rows = [
            (
                r["mode"],
                r["vendor_redis_memory_baseline_mib"],
                r["vendor_redis_memory_settled_mib"],
                r["vendor_redis_memory_delta_mib"],
                r["vendor_redis_memory_delta_bytes_per_payment"],
            )
            for r in sorted_rows
        ]
        config_dir = base / f"tps{int(tps)}_req{total}" / "vendor_resources"
        tasks.append(
            DrawTask(
                fn_name="stats_table",
                output_path=str(config_dir / "vendor_redis_memory_table.png"),
                kwargs={
                    "col_labels": [
                        "mode",
                        "redis_memory_baseline_mib",
                        "redis_memory_settled_mib",
                        "redis_memory_delta_mib",
                        "redis_memory_delta_bytes_per_payment",
                    ],
                    "rows": table_rows,
                    "title": (
                        f"Vendor Redis memory: baseline vs settled (tps={int(tps)})"
                    ),
                },
            )
        )

        # Same run's bytes-per-payment column as a bar, one bar per mode --
        # the table gives the exact figures, this gives the at-a-glance
        # comparison the table's five columns bury.
        bar_records = [
            {
                "mode": r["mode"],
                "bytes_per_payment": r["vendor_redis_memory_delta_bytes_per_payment"],
            }
            for r in sorted_rows
            if r.get("vendor_redis_memory_delta_bytes_per_payment") is not None
        ]
        if bar_records:
            tasks.append(
                DrawTask(
                    fn_name="per_payment_bar",
                    output_path=str(
                        config_dir
                        / "vendor_redis_memory_delta_bytes_per_payments_bar.png"
                    ),
                    kwargs={
                        "records": bar_records,
                        "title": (
                            "Vendor Redis memory delta per payment by mode "
                            f"(tps={int(tps)})"
                        ),
                        "value_key": "bytes_per_payment",
                        "y_axis_label": "Bytes / payment",
                    },
                )
            )

    # Aggregate baseline/settled/delta table across every config, one row per
    # (total payments, mode) -- keyed by total payments rather than TPS
    # because that is what actually drives Redis's memory footprint (more
    # payment keys written), not the rate they arrived at.
    aggregate_rows = [
        (
            int(r.get("total_requests") or 0),
            r["mode"],
            r["vendor_redis_memory_baseline_mib"],
            r["vendor_redis_memory_settled_mib"],
            r["vendor_redis_memory_delta_mib"],
        )
        for r in scalars
        if r.get("vendor_redis_memory_delta_mib") is not None
    ]
    if aggregate_rows:
        aggregate_rows.sort(key=lambda row: (row[0], row[1]))
        tasks.append(
            DrawTask(
                fn_name="stats_table",
                output_path=str(
                    base / "vendor_redis_memory_delta_vs_payments_table.png"
                ),
                kwargs={
                    "col_labels": [
                        "total_payments",
                        "mode",
                        "redis_memory_baseline_mib",
                        "redis_memory_settled_mib",
                        "redis_memory_delta_mib",
                    ],
                    "rows": aggregate_rows,
                    "title": (
                        "Vendor Redis memory: baseline vs settled, by total payments"
                    ),
                },
            )
        )

    return tasks


def generate_aggregate_plots(
    runs: List[Dict[str, Any]],
    output_dir: str,
    workers: int | None = None,
    parallel: bool = True,
    show_title: bool = True,
) -> List[str]:
    """Build and render the aggregate vs-TPS charts + Redis memory table. Returns written paths."""
    tasks = build_aggregate_draw_tasks(runs, output_dir)
    if not tasks:
        return []
    written, failures = draw_all(
        tasks, workers=workers, parallel=parallel, show_title=show_title
    )
    for f in failures:
        print(f"Aggregate draw failed for {f['output_path']}: {f['error']}")
    return written
