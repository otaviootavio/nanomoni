"""Metric-query definitions (PromQL) organized by payment mode."""

from typing import Any, Dict, Iterable, List

from .common import get_common_charts
from .signature import get_signature_charts, LATENCY_BUCKET_METRIC as _SIGNATURE_METRIC
from .payword import get_payword_charts, LATENCY_BUCKET_METRIC as _PAYWORD_METRIC
from .paytree import get_paytree_charts, LATENCY_BUCKET_METRIC as _PAYTREE_METRIC
from .paytree_first_opt import (
    get_paytree_first_opt_charts,
    LATENCY_BUCKET_METRIC as _PAYTREE_FIRST_OPT_METRIC,
)

# Single source of truth for mode -> latency-histogram bucket metric name,
# consumed by pipeline/latency.py to build the steady-state latency box/ECDF/
# violin queries instead of keeping a second copy of these strings.
LATENCY_BUCKET_METRIC_BY_MODE: Dict[str, str] = {
    "signature": _SIGNATURE_METRIC,
    "payword": _PAYWORD_METRIC,
    "paytree": _PAYTREE_METRIC,
    "paytree_first_opt": _PAYTREE_FIRST_OPT_METRIC,
}

# mode -> chart getter: the one place that knows how to turn a mode name into
# its chart list.
_MODE_CHART_GETTERS = {
    "signature": get_signature_charts,
    "payword": get_payword_charts,
    "paytree": get_paytree_charts,
    "paytree_first_opt": get_paytree_first_opt_charts,
}


def get_charts_for_modes(modes: Iterable[str]) -> List[Dict[str, Any]]:
    """Common charts plus only the charts for modes actually present.

    A mode's TPS/latency charts are included only when that mode is one of
    ``modes`` -- so a plan built from a benchmark_timing.json that only ran
    "payword", say, never issues signature/paytree queries that are guaranteed
    to return "No data returned" because that mode was never run.
    """
    # Copy: get_common_charts() returns the shared module-level list, so build on
    # a fresh list rather than mutating it in place (which would accumulate mode
    # charts across calls).
    charts = list(get_common_charts())
    for mode in sorted(set(modes)):
        getter = _MODE_CHART_GETTERS.get(mode)
        if getter is not None:
            charts += getter()
    return charts
