"""Shared Prometheus metric definitions for the vendor API payment routers.

Keeping the latency histogram buckets in one place ensures every payment
mode (signature, payword, paytree, ...) is sampled at the same resolution
and over the same range, so their frequency-distribution curves are
directly comparable.
"""

from __future__ import annotations

PAYMENT_DURATION_BUCKETS = (
    [round(0.5 * i, 1) for i in range(1, 21)]  # 0.5ms..10ms (0.5ms resolution)
    + [float(x) for x in range(15, 55, 5)]  # 15, 20, 25, ..., 50ms (5ms resolution)
    + [float("inf")]
)
