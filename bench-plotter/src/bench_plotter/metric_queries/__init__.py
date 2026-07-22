"""Dashboard queries module organized by payment mode."""

from typing import Any, Dict, Iterable, List

from .common import get_common_panels
from .signature import get_signature_panels, LATENCY_BUCKET_METRIC as _SIGNATURE_METRIC
from .payword import get_payword_panels, LATENCY_BUCKET_METRIC as _PAYWORD_METRIC
from .paytree import get_paytree_panels, LATENCY_BUCKET_METRIC as _PAYTREE_METRIC

# Single source of truth for mode -> latency-histogram bucket metric name,
# consumed by dashboard_processor.py's steady-state latency box/ECDF/violin
# builders instead of a second, hand-kept-in-sync copy of these strings.
LATENCY_BUCKET_METRIC_BY_MODE: Dict[str, str] = {
    "signature": _SIGNATURE_METRIC,
    "payword": _PAYWORD_METRIC,
    "paytree": _PAYTREE_METRIC,
}

# mode -> panel getter: the one place that knows how to turn a mode name into
# its panel list.
_MODE_PANEL_GETTERS = {
    "signature": get_signature_panels,
    "payword": get_payword_panels,
    "paytree": get_paytree_panels,
}


def get_dashboard_panels_for_modes(modes: Iterable[str]) -> List[Dict[str, Any]]:
    """Common panels plus only the panels for modes actually present.

    A mode's TPS/latency panels are included only when that mode is one of
    ``modes`` -- so a dashboard built from a benchmark_timing.json that only ran
    "payword", say, never issues signature/paytree queries that are guaranteed
    to return "No data returned" because that mode was never run.
    """
    # Copy: get_common_panels() returns the shared module-level list, so build on
    # a fresh list rather than mutating it in place (which would accumulate mode
    # panels across calls).
    panels = list(get_common_panels())
    for mode in sorted(set(modes)):
        getter = _MODE_PANEL_GETTERS.get(mode)
        if getter is not None:
            panels += getter()
    return panels
