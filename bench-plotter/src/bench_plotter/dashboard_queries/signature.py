#!/usr/bin/env python3
"""Signature payment mode specific dashboard queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# reused by dashboard_processor.py's steady-state latency box/ECDF/violin
# builders instead of duplicating the string there.
LATENCY_BUCKET_METRIC = "payment_request_duration_milliseconds_bucket"

# Signature-specific TPS metrics panels
SIGNATURE_PANELS: List[Dict[str, Any]] = [
    # Row: TPS Metrics
    {"title": "TPS Metrics", "type": "row", "section": "tps_metrics"},
    {
        "title": "Vendor Payment TPS (success)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {
                "expr": 'rate(payment_requests_total{job="vendor-api", status="success"}[1m])',
                "legendFormat": "Payment Requests",
            },
        ],
    },
    # Row: Vendor Payment Metrics (vendor-api)
    {
        "title": "Vendor Payment Metrics (vendor-api)",
        "type": "row",
        "section": "tps_metrics",
    },
    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {
                "expr": f'histogram_quantile(0.99, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[1m])) by (le))',
                "legendFormat": "Payment P99",
            },
            {
                "expr": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[1m])) by (le))',
                "legendFormat": "Payment P95",
            },
            {
                "expr": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[1m])) by (le))',
                "legendFormat": "Payment P50",
            },
        ],
    },
]


def get_signature_panels() -> List[Dict[str, Any]]:
    """Return signature-specific panels."""
    return SIGNATURE_PANELS
