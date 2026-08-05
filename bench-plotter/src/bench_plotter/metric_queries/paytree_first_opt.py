#!/usr/bin/env python3
"""paytree_first_opt payment mode PromQL metric queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# consumed by pipeline/latency.py to build the steady-state latency box/ECDF/violin
# queries instead of duplicating the string there.
LATENCY_BUCKET_METRIC = "paytree_first_opt_payment_request_duration_milliseconds_bucket"

# Single source of truth for this mode's payment counter, consumed by
# saturation/aggregate.py to build the achieved-TPS query.
PAYMENT_COUNTER_METRIC = "paytree_first_opt_payment_requests_total"

# Paytree-first-opt-specific TPS metrics charts
PAYTREE_FIRST_OPT_CHARTS: List[Dict[str, Any]] = [
    {
        "title": "Vendor Payment TPS (success)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'rate({PAYMENT_COUNTER_METRIC}{{job="vendor-api", status="success"}}[10s])',
                "legend": "Paytree First-Opt",
            },
        ],
    },
    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'histogram_quantile(0.99, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree First-Opt P99",
            },
            {
                "promql": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree First-Opt P95",
            },
            {
                "promql": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[10s])) by (le))',
                "legend": "Paytree First-Opt P50",
            },
        ],
    },
]


def get_paytree_first_opt_charts() -> List[Dict[str, Any]]:
    """Return paytree_first_opt-specific charts."""
    return PAYTREE_FIRST_OPT_CHARTS
