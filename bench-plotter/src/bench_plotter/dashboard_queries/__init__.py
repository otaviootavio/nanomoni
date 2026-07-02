"""Dashboard queries module organized by payment mode."""

from typing import Any, Dict, List

from .common import get_common_panels
from .signature import get_signature_panels
from .payword import get_payword_panels
from .paytree import get_paytree_panels


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
