"""Transform stage for the client-egress-per-payment table.

Turns the client's steady-state egress *rate* into a *size*: dividing KiB/s by
the payments/s that produced it leaves the bytes one payment request puts on the
wire, which is the number to compare across payment modes (a mode whose proof
grows with the payment index costs bandwidth the KiB/s chart only shows
indirectly, mixed together with the load level). Plan-side job construction
lives in :mod:`.resource`.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from bench_plotter.plotting.windowing import steady_state_samples

from .model import DrawTask, PlotJob, ResultCache
from .series_runs import runs_from_series

_COLUMNS = (
    "mode",
    "target_tps",
    "egress_kib_s_mean",
    "kib_per_payment",
    "bytes_per_payment",
)

_BYTES_PER_KIB = 1024.0


def transform_per_payment_table(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build the per-payment request-size table from a cached rate series."""
    runs = runs_from_series(job.params["series"], cache)
    tps_by_mode: Dict[str, Any] = job.params["tps_by_mode"]

    rows: List[List[Any]] = []
    for run in runs:
        mode = run["interval_mode"]
        tps = tps_by_mode.get(mode)
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
