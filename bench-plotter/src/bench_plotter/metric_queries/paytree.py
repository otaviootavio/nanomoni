#!/usr/bin/env python3
"""Paytree payment mode specific dashboard queries."""

from typing import Any, Dict, List

# Single source of truth for this mode's latency-histogram bucket metric name,
# reused by dashboard_processor.py's steady-state latency box/ECDF/violin
# builders instead of duplicating the string there.
LATENCY_BUCKET_METRIC = "paytree_payment_request_duration_milliseconds_bucket"

# Paytree-specific TPS metrics panels
PAYTREE_PANELS: List[Dict[str, Any]] = [
    # Row: TPS Metrics
    {"title": "TPS Metrics", "type": "row", "section": "tps_metrics"},
    {
        "title": "Vendor Payment TPS (success)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {
                "expr": 'rate(paytree_payment_requests_total{job="vendor-api", status="success"}[1m])',
                "legendFormat": "Paytree",
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
                "legendFormat": "Paytree P99",
            },
            {
                "expr": f'histogram_quantile(0.95, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[1m])) by (le))',
                "legendFormat": "Paytree P95",
            },
            {
                "expr": f'histogram_quantile(0.50, sum(rate({LATENCY_BUCKET_METRIC}{{job="vendor-api", status="success"}}[1m])) by (le))',
                "legendFormat": "Paytree P50",
            },
        ],
    },
]


def get_paytree_panels() -> List[Dict[str, Any]]:
    """Return paytree-specific panels."""
    return PAYTREE_PANELS
