#!/usr/bin/env python3
"""Signature payment mode specific dashboard queries."""

from typing import Any, Dict, List

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
    {
        "title": "Vendor Payment Duration Average (ms)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {
                "expr": 'histogram_quantile(0.99, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P99",
            },
            {
                "expr": 'histogram_quantile(0.95, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P95",
            },
            {
                "expr": 'histogram_quantile(0.50, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P50",
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
                "expr": 'histogram_quantile(0.99, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P99",
            },
            {
                "expr": 'histogram_quantile(0.95, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P95",
            },
            {
                "expr": 'histogram_quantile(0.50, sum(rate(payment_request_duration_milliseconds_bucket{job="vendor-api", status="success"}[1m])) by (le))',
                "legendFormat": "Payment P50",
            },
        ],
    },
    {
        "title": "Frequency Distribution of Payment Latency (vendor-api)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {
                "expr": 'sum(payment_request_duration_milliseconds_bucket{job="vendor-api",status="success"}) by (le)',
                "legendFormat": "__auto",
            },
        ],
    },
]


def get_signature_panels() -> List[Dict[str, Any]]:
    """Return signature-specific panels."""
    return SIGNATURE_PANELS
