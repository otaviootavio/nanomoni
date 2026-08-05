#!/usr/bin/env python3
"""paytree payment mode PromQL metric queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# consumed by pipeline/latency.py to build the steady-state latency box/ECDF/violin
# queries instead of duplicating the string there.
LATENCY_BUCKET_METRIC = "paytree_std_payment_request_duration_milliseconds_bucket"

# Single source of truth for this mode's payment counter, consumed by
# saturation/aggregate.py to build the achieved-TPS query.
PAYMENT_COUNTER_METRIC = "paytree_std_payment_requests_total"

# Paytree-specific TPS metrics charts
PAYTREE_CHARTS: List[Dict[str, Any]] = [
    {
        "title": "Vendor Payment TPS (success)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'rate({PAYMENT_COUNTER_METRIC}{{job="vendor-api", status="success"}}[10s])',
                "legend": "Paytree",
            },
        ],
    },
    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'histogram_quantile(0.99, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree P99",
            },
            {
                "promql": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree P95",
            },
            {
                "promql": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree P50",
            },
        ],
    },
]


def get_paytree_charts() -> List[Dict[str, Any]]:
    """Return paytree-specific charts."""
    return PAYTREE_CHARTS
