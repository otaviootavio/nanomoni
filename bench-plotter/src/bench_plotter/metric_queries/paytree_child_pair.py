#!/usr/bin/env python3
"""paytree_child_pair payment mode PromQL metric queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# consumed by pipeline/latency.py to build the steady-state latency box/ECDF/
# violin queries instead of duplicating the string there.
LATENCY_BUCKET_METRIC = (
    "paytree_child_pair_payment_request_duration_milliseconds_bucket"
)

# Single source of truth for this mode's payment counter, consumed by
# saturation/aggregate.py to build the achieved-TPS query.
PAYMENT_COUNTER_METRIC = "paytree_child_pair_payment_requests_total"

# Paytree-child-pair-specific TPS metrics charts
PAYTREE_CHILD_PAIR_CHARTS: List[Dict[str, Any]] = [
    {
        "title": "Vendor Payment TPS (success)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'rate({PAYMENT_COUNTER_METRIC}{{job="vendor-api", status="success"}}[10s])',
                "legend": "Paytree Child-Pair",
            },
        ],
    },
    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'histogram_quantile(0.99, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree Child-Pair P99",
            },
            {
                "promql": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree Child-Pair P95",
            },
            {
                "promql": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree Child-Pair P50",
            },
        ],
    },
]


def get_paytree_child_pair_charts() -> List[Dict[str, Any]]:
    """Return paytree_child_pair-specific charts."""
    return PAYTREE_CHILD_PAIR_CHARTS
