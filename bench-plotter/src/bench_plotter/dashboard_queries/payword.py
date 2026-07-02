#!/usr/bin/env python3
"""Payword payment mode specific dashboard queries."""

# Payword-specific TPS metrics panels
PAYWORD_PANELS = [
    # Row: TPS Metrics
    {"title": "TPS Metrics", "type": "row", "section": "tps_metrics"},

    {
        "title": "Vendor Payment TPS (success)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {"expr": "rate(payword_payment_requests_total{job=\"vendor-api\", status=\"success\"}[30s])", "legendFormat": "Payword"},
        ],
    },

    {
        "title": "Vendor Payment Duration Average (ms)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {"expr": "histogram_quantile(0.99, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P99"},
            {"expr": "histogram_quantile(0.95, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P95"},
            {"expr": "histogram_quantile(0.50, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P50"},
        ],
    },

    # Row: Vendor Payment Metrics (vendor-api)
    {"title": "Vendor Payment Metrics (vendor-api)", "type": "row", "section": "tps_metrics"},

    {
        "title": "Vendor Payment Duration Quantiles (ms)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {"expr": "histogram_quantile(0.99, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P99"},
            {"expr": "histogram_quantile(0.95, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P95"},
            {"expr": "histogram_quantile(0.50, sum(rate(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\", status=\"success\"}[1m])) by (le))", "legendFormat": "Payword P50"},
        ],
    },

    {
        "title": "Frequency Distribution of Payment Latency (vendor-api)",
        "type": "timeseries",
        "section": "tps_metrics",
        "targets": [
            {"expr": "sum(payword_payment_request_duration_milliseconds_bucket{job=\"vendor-api\",status=\"success\"}) by (le)", "legendFormat": "__auto"},
        ],
    },
]


def get_payword_panels():
    """Return payword-specific panels."""
    return PAYWORD_PANELS
