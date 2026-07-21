"""Naming and classification predicates used to categorize dashboard panels.

Pure string helpers with no dependency on the plan model, kept separate from
``plan.py`` so panel *classification* (what a panel is, what it's called) is
isolated from job *construction* (turning classified panels into query plans).
Migrated verbatim in behaviour from the old dashboard_processor.
"""

from __future__ import annotations

import re
from typing import Optional


def extract_unit_from_title(title: str) -> str:
    """Y-axis label from a title's trailing unit, e.g. "(MiB)" -> "Value (MiB)"."""
    match = re.search(r"\(([^)]+)\)", title)
    return f"Value ({match.group(1)})" if match else "Value"


def sanitize_filename(name: str) -> str:
    """Lowercase, replace unsafe characters, collapse repeats -> filename stem."""
    out = name.lower()
    for ch in ' ()/\\:*?"<>|':
        out = out.replace(ch, "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def is_tps_panel(panel_title: str, legend_format: str, expr: str) -> bool:
    """True for throughput/latency-quantile/payment panels (overlaid across modes)."""
    title = (panel_title or "").lower()
    if "distribution" in title:  # frequency distributions are histograms
        return False
    legend = (legend_format or "").lower()
    ex = (expr or "").lower()
    return (
        "tps" in title
        or "tps" in legend
        or "tps" in ex
        or "duration" in title
        or "quantile" in title
        or "payment" in title
    )


def extract_payment_mode_from_expr(expr: str) -> str:
    """Derive the payment mode from a PromQL metric prefix."""
    ex = expr.lower()
    if "paytree_" in ex:
        return "paytree"
    if "payword_" in ex:
        return "payword"
    return "signature"


def quantile_label(legend_format: str) -> Optional[str]:
    """Return 'P99'/'P95'/'P50' if the legend names a quantile, else None."""
    lf = legend_format.lower()
    for q in ("p99", "p95", "p50"):
        if q in lf:
            return q.upper()
    return None
