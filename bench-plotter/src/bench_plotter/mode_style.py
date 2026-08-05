"""Shared per-payment-mode visual identity and vs-TPS series grouping.

Extracted from ``sweep/aggregate.py`` so both it and ``profiling/aggregate.py``
can build "one line per mode" vs-TPS charts with the same stable
color/marker assignment, without either module depending on the other
(``sweep`` already depends on ``profiling`` for the profiling stage, so the
reverse edge would be circular).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from bench_plotter.plotting.common import PALETTE

# Stable visual identity per payment mode (sorted-mode index into the palette).
MODE_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
KNOWN_MODES = (
    "paytree",
    "paytree_first_opt",
    "paytree_child_pair",
    "payword",
    "signature",
)


def mode_style(mode: str) -> Dict[str, str]:
    """Return ``{color, marker}`` for a payment mode (stable across charts)."""
    try:
        idx = KNOWN_MODES.index(mode)
    except ValueError:
        idx = abs(hash(mode)) % len(PALETTE)
    return {
        "color": PALETTE[idx % len(PALETTE)],
        "marker": MODE_MARKERS[idx % len(MODE_MARKERS)],
    }


def series_by_mode(
    scalars: List[Dict[str, Any]],
    y_key: str,
    label_suffix: str = "",
    linestyle: str = "-",
) -> List[Dict[str, Any]]:
    """Group (tps, y) points by mode for one y-field, with stable mode styling."""
    by_mode: Dict[str, List[Tuple[float, float]]] = {}
    for row in scalars:
        y = row.get(y_key)
        if y is None:
            continue
        mode = row["mode"]
        by_mode.setdefault(mode, []).append((row["tps"], float(y)))

    series: List[Dict[str, Any]] = []
    for mode in sorted(by_mode):
        points = sorted(by_mode[mode], key=lambda p: p[0])
        label = f"{mode}{label_suffix}" if label_suffix else mode
        style = mode_style(mode)
        series.append(
            {
                "label": label,
                "x_values": [p[0] for p in points],
                "y_values": [p[1] for p in points],
                "color": style["color"],
                "marker": style["marker"],
                "linestyle": linestyle,
            }
        )
    return series
