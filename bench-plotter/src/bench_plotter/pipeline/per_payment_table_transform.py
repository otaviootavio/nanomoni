"""Transform stage for the client-egress-per-payment table.

Turns the client's steady-state egress *rate* into a *size*: dividing KiB/s by
the payments/s that produced it leaves the bytes one payment request puts on the
wire, which is the number to compare across payment modes (a mode whose proof
grows with the payment index costs bandwidth the KiB/s chart only shows
indirectly, mixed together with the load level). Plan-side job construction
lives in :mod:`.resource`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.saturation.aggregate import samples_from_payload, sustained_rate

from .model import DrawTask, PlotJob, QuerySpec, ResultCache
from .series_runs import runs_from_series

_COLUMNS = (
    "mode",
    "achieved_tps",
    "egress_kib_s_mean",
    "kib_per_payment",
    "bytes_per_payment",
)

_BYTES_PER_KIB = 1024.0


def _achieved_tps_for_mode(
    mode: str,
    cache: ResultCache,
    achieved_tps_specs: Dict[str, QuerySpec],
    fallback_tps: Optional[float],
) -> Optional[float]:
    """Prefer the vendor's sustained success rate; fall back to target TPS."""
    spec = achieved_tps_specs.get(mode)
    if spec is not None:
        measured = sustained_rate(samples_from_payload(cache.get(spec)))
        if measured is not None and measured > 0:
            return float(measured)
    if fallback_tps is not None and float(fallback_tps) > 0:
        return float(fallback_tps)
    return None


def _per_payment_rows(job: PlotJob, cache: ResultCache) -> List[List[Any]]:
    """Shared (mode, achieved TPS, KiB/s, KiB/payment, bytes/payment) rows for
    both the table and bar-chart renderings of this job's cached rate series."""
    runs = runs_from_series(job.params["series"], cache)
    tps_by_mode: Dict[str, Any] = job.params["tps_by_mode"]
    achieved_tps_specs: Dict[str, QuerySpec] = (
        job.params.get("achieved_tps_specs") or {}
    )

    rows: List[List[Any]] = []
    for run in runs:
        mode = run["interval_mode"]
        fallback = tps_by_mode.get(mode)
        tps = _achieved_tps_for_mode(mode, cache, achieved_tps_specs, fallback)
        samples = steady_state_samples(run["values"])
        if not tps or not samples:
            continue
        kib_per_second = float(np.mean(samples))
        kib_per_payment = kib_per_second / float(tps)
        rows.append(
            [
                mode,
                float(tps),
                kib_per_second,
                kib_per_payment,
                kib_per_payment * _BYTES_PER_KIB,
            ]
        )
    return rows


def transform_per_payment_table(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build the per-payment request-size table from a cached rate series."""
    rows = _per_payment_rows(job, cache)
    if not rows:
        print(f"No steady-state samples for per-payment table: {job.title}")
        return []
    rows.sort(key=lambda row: str(row[0]))
    return [
        DrawTask(
            fn_name="stats_table",
            output_path=job.output_path,
            kwargs={
                "col_labels": list(_COLUMNS),
                "rows": rows,
                "title": job.title,
            },
        )
    ]


def transform_per_payment_bar(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build the per-payment request-size bar chart from a cached rate series.

    One bar per mode (KiB/payment), sorted descending so the mode putting the
    most bytes on the wire per payment reads first, left to right.
    """
    rows = _per_payment_rows(job, cache)
    if not rows:
        print(f"No steady-state samples for per-payment bar chart: {job.title}")
        return []
    records = [
        {"mode": mode, "kib_per_payment": kib_per_payment}
        for mode, _tps, _kib_s, kib_per_payment, _bytes in rows
    ]
    return [
        DrawTask(
            fn_name="per_payment_bar",
            output_path=job.output_path,
            kwargs={"records": records, "title": job.title},
        )
    ]
