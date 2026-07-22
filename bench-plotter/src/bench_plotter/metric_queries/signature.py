#!/usr/bin/env python3
"""signature payment mode PromQL metric queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# consumed by pipeline/latency.py to build the steady-state latency box/ECDF/violin
# queries instead of duplicating the string there.
LATENCY_BUCKET_METRIC = "payment_request_duration_milliseconds_bucket"

# Signature-specific TPS metrics charts
SIGNATURE_CHARTS: List[Dict[str, Any]] = [
    {
        "title": "Vendor Payment TPS (success)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": 'rate(payment_requests_total{job="vendor-api", status="success"}[30s])',
                "legend": "Payment Requests",
            },
        ],
    },
    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "section": "tps_metrics",
        "queries": [
            {
                "promql": f'histogram_quantile(0.99, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[30s])) by (le))',
                "legend": "Payment P99",
            },
            {
                "promql": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[30s])) by (le))',
                "legend": "Payment P95",
            },
            {
                "promql": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[30s])) by (le))',
                "legend": "Payment P50",
            },
        ],
    },
]


def get_signature_charts() -> List[Dict[str, Any]]:
    """Return signature-specific charts."""
    return SIGNATURE_CHARTS
