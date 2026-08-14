"""Per-run CPU profiling via Pyroscope: flame graphs + macro/micro time extraction.

Mirrors ``sweep/aggregate.py``'s shape (per-run window fetch, bounded
concurrency, DrawTask emission) but against Pyroscope instead of Prometheus,
and reduces a merged call tree instead of a value time series.

Pyroscope's ``/render`` returns one aggregated tree over the requested
``[from, until]`` window, not a value series, so the warm-up/cool-down
trimming that ``steady_state_samples`` does for Prometheus series (drop
samples outside +/-20% of the median) doesn't apply here -- and it isn't
needed. The run window is queried whole, because the harness already isolates
it: ``run_benchmark.sh`` sleeps before launching the client and drains after
it exits, so ``[start_ms, finish_ms]`` has idle margins at both ends.
Verified against a live run: padding the window outward by up to 15s changes
neither the payment count nor any CPU bucket, for every mode.

Trimming a fraction off each end (a previous approach) actively hurt. CPU
comes back in 15s buckets (``timeline.durationDelta`` in the response) and
whole overlapping buckets are returned, while the Prometheus payment counter
follows the requested window much more finely. Sliding the window therefore
moved numerator and denominator on different grids, adding ~10% of scatter to
every per-payment number, and cutting into the front of the window truncated
the counter delta -- the payment count is only complete when the window
starts in an idle margin, before the first payment.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from bench_plotter import pyroscope_fetch
from bench_plotter.flamebearer import (
    build_tree,
    outermost_nodes,
    root_total_ticks,
    sample_rate,
    sum_ticks_by_name,
    sum_ticks_within,
)
from bench_plotter.metric_queries import PAYMENT_COUNTER_METRIC_BY_MODE
from bench_plotter.mode_style import series_by_mode
from bench_plotter.pipeline.draw import draw_all
from bench_plotter.pipeline.model import DrawTask
from bench_plotter.plotting.profile_bar_renderer import (
    _CRYPTO_COLOR,
    _DB_READ_COLOR,
    _DB_WRITE_COLOR,
)
from bench_plotter.profiling.mode_functions import (
    MODE_FUNCTIONS,
    RUN_ENDPOINT_FUNCTION,
    VENDOR_PROFILE_QUERY,
)
from bench_plotter.prometheus_fetch import query_range
from bench_plotter.prometheus_matrix import matrix_to_per_series_charts

_MAX_CONCURRENCY = 4

# Absolute CPU-time field -> its per-payment counterpart (milliseconds).
_PER_PAYMENT_FIELDS = {
    "crypto_time_s": "crypto_ms_per_payment",
    "db_read_time_s": "db_read_ms_per_payment",
    "db_write_time_s": "db_write_ms_per_payment",
    "other_time_s": "other_ms_per_payment",
}


def _extract_record(payload: Dict[str, Any], mode: str, tps: float) -> Dict[str, Any]:
    root = build_tree(payload)
    rate = sample_rate(payload)
    if rate <= 0:
        raise ValueError("flamebearer sampleRate is not positive")

    def seconds(ticks: int) -> float:
        return ticks / rate

    cfg = MODE_FUNCTIONS[mode]
    run_endpoint_ticks = sum(sum_ticks_by_name(root, [RUN_ENDPOINT_FUNCTION]).values())

    endpoint_nodes = outermost_nodes(root, cfg["endpoint"])
    macro_ticks = sum(n.total_ticks for n in endpoint_nodes)

    # The db buckets are measured at the store primitives (reads and writes go
    # through different ones), so the three micro buckets are disjoint subtrees
    # of the endpoint and need no netting out of one another. other is the
    # residual of macro: framework, request/response handling, serialization,
    # repository bookkeeping and the issuer round trip.
    micro_ticks = sum_ticks_within(
        endpoint_nodes,
        cfg["crypto"] + cfg["db_read"] + cfg["db_write"],
    )

    def bucket_ticks(names: List[str]) -> int:
        return sum(micro_ticks.get(name, 0) for name in names)

    crypto_ticks = bucket_ticks(cfg["crypto"])
    db_read_ticks = bucket_ticks(cfg["db_read"])
    db_write_ticks = bucket_ticks(cfg["db_write"])
    other_ticks = max(
        0,
        macro_ticks - crypto_ticks - db_read_ticks - db_write_ticks,
    )

    return {
        "mode": mode,
        "tps": tps,
        "total_time_s": seconds(root_total_ticks(payload)),
        "run_endpoint_time_s": seconds(run_endpoint_ticks),
        "macro_time_s": seconds(macro_ticks),
        "crypto_time_s": seconds(crypto_ticks),
        "db_read_time_s": seconds(db_read_ticks),
        "db_write_time_s": seconds(db_write_ticks),
        "other_time_s": seconds(other_ticks),
        "payload": payload,
    }


def _counter_delta(payload: Dict[str, Any]) -> Optional[float]:
    """Sum of each series' last-minus-first raw value.

    ``None`` if no series had at least two samples in the window (nothing to
    take a delta of), so the caller can tell "no data" apart from "zero
    payments".
    """
    charts = matrix_to_per_series_charts(payload.get("data", {}).get("result", []))
    total = 0.0
    found = False
    for chart in charts:
        data = [v for v in (chart.get("data") or []) if v is not None]
        if len(data) < 2:
            continue
        found = True
        total += data[-1] - data[0]
    return total if found else None


async def _payments_served(
    mode: str,
    start: float,
    end: float,
) -> Optional[float]:
    """Payments the vendor's own success counter recorded inside the profiled
    window.

    This used to be modeled from the target TPS and ``total_requests``,
    assuming traffic ran at the target rate starting at the run's nominal
    start. That assumption breaks for e.g. signature mode, whose client
    blocks on a bulk client-side pre-signing phase (``client_pay_chan.py``)
    before sending a single request -- sometimes for minutes -- so the model
    counted payments the profiled window couldn't possibly have seen yet,
    understating every per-payment CPU number derived from it. Reading the
    counter directly (the same source ``saturation/aggregate.py`` uses for
    achieved TPS) sidesteps modeling traffic altogether: whatever the vendor
    actually served in ``[start, end]`` is what the profiled CPU time was
    spent on, however traffic was paced or delayed.

    Raises whatever ``query_range`` raises (unreachable/erroring Prometheus)
    rather than degrading to a guess -- a per-payment number computed from a
    wrong payment count is worse than no number at all.
    """
    metric = PAYMENT_COUNTER_METRIC_BY_MODE.get(mode)
    if not metric:
        return None
    payload = await query_range(
        query=f'{metric}{{job="vendor-api", status="success"}}',
        start_unix=start,
        end_unix=end,
    )
    return _counter_delta(payload)


def _add_per_payment_fields(record: Dict[str, Any]) -> None:
    """Fill the ``*_ms_per_payment`` fields from ``profile_payments``."""
    payments = record.get("profile_payments")
    for source, target in _PER_PAYMENT_FIELDS.items():
        record[target] = (
            record[source] / payments * 1000.0 if payments and payments > 0 else None
        )


async def _fetch_run_profile(
    run: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    mode = run.get("mode")
    tps = run.get("tps")
    if mode is None or tps is None or mode not in MODE_FUNCTIONS:
        return None
    ts = run.get("prometheus_timestamps", {}) or {}
    start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
    if not start_ms or not finish_ms:
        return None

    start, end = start_ms / 1000.0, finish_ms / 1000.0

    async with sem:
        try:
            payload = await pyroscope_fetch.render(
                query=VENDOR_PROFILE_QUERY,
                start_unix=start,
                end_unix=end,
            )
        except Exception as exc:  # noqa: BLE001 - recorded as a skipped run
            print(f"  pyroscope query failed for mode={mode} tps={tps}: {exc}")
            return None

        # Not caught here: unlike a down Pyroscope (skip just this one run), a
        # down/erroring Prometheus means the payment count -- and therefore
        # every per-payment number this profiling stage produces -- can't be
        # trusted, so the failure is left to propagate up to
        # build_profile_draw_tasks, which aborts the whole profiling stage.
        payments = await _payments_served(str(mode), start, end)

    try:
        record = _extract_record(payload, mode, float(tps))
    except Exception as exc:  # noqa: BLE001 - recorded as a skipped run
        print(f"  profile extraction failed for mode={mode} tps={tps}: {exc}")
        return None

    record["total_requests"] = run.get("total_requests")
    record["profile_payments"] = payments
    _add_per_payment_fields(record)
    return record


async def _collect_profiles(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    results = await asyncio.gather(*(_fetch_run_profile(r, sem) for r in runs))
    return [r for r in results if r is not None]


def _highlight_for_mode(mode: str) -> Dict[str, str]:
    cfg = MODE_FUNCTIONS[mode]
    highlight = {name: _CRYPTO_COLOR for name in cfg["crypto"]}
    highlight.update({name: _DB_READ_COLOR for name in cfg["db_read"]})
    highlight.update({name: _DB_WRITE_COLOR for name in cfg["db_write"]})
    return highlight


def build_profile_draw_tasks(
    runs: List[Dict[str, Any]],
    output_dir: str,
) -> List[DrawTask]:
    """Fetch per-run profiles and return DrawTasks for flame graphs + the
    aggregate macro/micro comparison. Returns ``[]`` (not raises) on any
    failure to fetch/parse -- a down Pyroscope must not break the rest of the
    sweep's plots."""
    if not runs:
        return []
    print(f"Profiling {len(runs)} run(s) via Pyroscope...")
    try:
        records = asyncio.run(_collect_profiles(runs))
    except Exception as exc:  # noqa: BLE001 - profiling is best-effort
        print(f"Profiling stage failed: {exc}")
        return []
    if not records:
        print("No profile records available; skipping profiling charts")
        return []

    base = Path(output_dir)
    tasks: List[DrawTask] = []
    for record in records:
        mode = record["mode"]
        tps = int(record["tps"])
        total = int(record.get("total_requests") or 0)
        cfg = MODE_FUNCTIONS[mode]
        flame_path = base / f"tps{tps}_req{total}" / "profile" / f"flame_{mode}.png"
        tasks.append(
            DrawTask(
                fn_name="flame_graph",
                output_path=str(flame_path),
                kwargs={
                    "flamebearer_payload": record["payload"],
                    "title": f"{mode} vendor CPU flame graph (tps={tps})",
                    "highlight": _highlight_for_mode(mode),
                    # Focus on the mode's own receive_*_payment endpoint
                    # rather than run_endpoint_function -- it skips straight
                    # to app code instead of also including the FastAPI
                    # dispatch/dependency-injection frames above it.
                    "focus": cfg["endpoint"],
                },
            )
        )

    bar_records = [{k: v for k, v in r.items() if k != "payload"} for r in records]

    # One bar chart per TPS (not faceted into a single image), written into that
    # TPS's own profile folder alongside that config's flame graphs.
    for tps in sorted({r["tps"] for r in bar_records}):
        rows = [r for r in bar_records if r["tps"] == tps]
        total = int(rows[0].get("total_requests") or 0)
        tasks.append(
            DrawTask(
                fn_name="profile_macro_micro_bar",
                output_path=str(
                    base
                    / f"tps{int(tps)}_req{total}"
                    / "profile"
                    / "profile_macro_micro.png"
                ),
                kwargs={
                    "records": rows,
                    "title": (
                        f"Vendor CPU time per payment: macro (endpoint) vs micro "
                        f"(crypto/db read/db write) by mode "
                        f"(tps={int(tps)})"
                    ),
                },
            )
        )

    # The combined (tps, mode) table, as both a CSV and a rendered PNG.
    tasks.append(
        DrawTask(
            fn_name="profile_macro_micro_table",
            output_path=str(base / "profile_macro_micro_table.png"),
            kwargs={
                "records": bar_records,
                "title": "Vendor CPU time by mode and TPS",
            },
        )
    )

    # The "general view": how each time category evolves across the sweep, one
    # line per mode, mirroring the other vs-TPS aggregate charts. Each category
    # gets two charts -- the CPU time the profiled window measured, and that time
    # divided by the payments it was spent on. The absolute chart rises with TPS
    # simply because there is more traffic in the window; only the per-payment
    # one shows whether a payment got cheaper or more expensive.
    for key, filename, label, y_label in (
        (
            "crypto_time_s",
            "crypto_time_vs_tps.png",
            "Crypto (verify) time",
            "CPU time (s)",
        ),
        (
            "db_read_time_s",
            "db_read_time_vs_tps.png",
            "DB read (mget) time",
            "CPU time (s)",
        ),
        (
            "db_write_time_s",
            "db_write_time_vs_tps.png",
            "DB write (run_script) time",
            "CPU time (s)",
        ),
        (
            "other_time_s",
            "other_time_vs_tps.png",
            "Other (unaccounted) time",
            "CPU time (s)",
        ),
        (
            "crypto_ms_per_payment",
            "crypto_time_per_payment_vs_tps.png",
            "Crypto (verify) time per payment",
            "CPU time per payment (ms)",
        ),
        (
            "db_read_ms_per_payment",
            "db_read_time_per_payment_vs_tps.png",
            "DB read (mget) time per payment",
            "CPU time per payment (ms)",
        ),
        (
            "db_write_ms_per_payment",
            "db_write_time_per_payment_vs_tps.png",
            "DB write (run_script) time per payment",
            "CPU time per payment (ms)",
        ),
        (
            "other_ms_per_payment",
            "other_time_per_payment_vs_tps.png",
            "Other (unaccounted) time per payment",
            "CPU time per payment (ms)",
        ),
    ):
        series = series_by_mode(bar_records, key)
        if not series:
            continue
        tasks.append(
            DrawTask(
                fn_name="sweep_line",
                output_path=str(base / filename),
                kwargs={
                    "series_list": series,
                    "title": f"{label} vs TPS",
                    "x_axis_label": "TPS",
                    "y_axis_label": y_label,
                },
            )
        )

    return tasks


def generate_profile_outputs(
    runs: List[Dict[str, Any]],
    output_dir: str,
    workers: int | None = None,
    parallel: bool = True,
) -> List[str]:
    """Build and render per-run flame graphs + the aggregate comparison chart."""
    try:
        tasks = build_profile_draw_tasks(runs, output_dir)
    except Exception as exc:  # noqa: BLE001 - profiling is best-effort
        print(f"Profiling stage failed to build tasks: {exc}")
        return []
    if not tasks:
        return []
    written, failures = draw_all(tasks, workers=workers, parallel=parallel)
    for f in failures:
        print(f"Profile draw failed for {f['output_path']}: {f['error']}")
    return written
