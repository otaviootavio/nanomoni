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

# mode -> panel getter, shared by get_dashboard_panels("all") and
# get_dashboard_panels_for_modes so there is one place that knows how to turn
# a mode name into its panel list.
_MODE_PANEL_GETTERS = {
    "signature": get_signature_panels,
    "payword": get_payword_panels,
    "paytree": get_paytree_panels,
}


def get_dashboard_panels_for_modes(modes: Iterable[str]) -> List[Dict[str, Any]]:
    """Common panels plus only the panels for modes actually present.

    Unlike ``get_dashboard_panels("all")``, this never includes a mode's
    TPS/latency/distribution panels unless that mode is one of ``modes`` --
    so a dashboard built from a benchmark_timing.json that only ran
    "payword", say, never issues signature/paytree queries that are
    guaranteed to return "No data returned" because that mode was never run.
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


def get_dashboard_panels(mode: str = "all") -> List[Dict[str, Any]]:
    """
    Get dashboard panels for a specific payment mode or all modes.

    Args:
        mode: Payment mode - "signature", "payword", "paytree", or "all"

    Returns:
        List of panel dictionaries with keys: title, type, section, targets
    """
    common_panels = get_common_panels()

    if mode == "signature":
        return common_panels + get_signature_panels()
    elif mode == "payword":
        return common_panels + get_payword_panels()
    elif mode == "paytree":
        return common_panels + get_paytree_panels()
    elif mode == "all":
        # Combine all payment mode panels
        return (
            common_panels
            + get_signature_panels()
            + get_payword_panels()
            + get_paytree_panels()
        )
    else:
        raise ValueError(
            f"Unknown mode: {mode}. Use 'signature', 'payword', 'paytree', or 'all'"
        )


if __name__ == "__main__":
    # Test the dashboard structure
    panels = get_dashboard_panels()
    print(f"Dashboard has {len(panels)} panels")

    # Show sections
    sections = set(panel["section"] for panel in panels if panel["type"] != "row")
    print(f"Sections: {sorted(sections)}")

    # Show a sample panel
    for panel in panels:
        if panel["type"] != "row":
            print(f"\nSample panel: {panel['title']}")
            print(f"  Section: {panel['section']}")
            print(f"  Targets: {len(panel['targets'])}")
            if panel["targets"]:
                print(f"  First target: {panel['targets'][0]['legendFormat']}")
            break
