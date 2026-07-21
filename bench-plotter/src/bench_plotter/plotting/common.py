"""Common utilities shared across plotting modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.figure import Figure

# Colorblind-safe categorical palette (light-mode steps), validated against the
# dataviz six-check procedure: adjacent-pair CVD deltaE >= 8 and normal-vision
# deltaE >= 15. Slots are assigned in fixed order (never cycled) so a given
# scheme keeps the same hue across every figure. Order: blue, green, magenta,
# yellow, aqua, orange, violet, red.
PALETTE = [
    "#2a78d6",
    "#008300",
    "#e87ba4",
    "#eda100",
    "#1baf7a",
    "#eb6834",
    "#4a3aa7",
    "#e34948",
]

_THEME_APPLIED = False


def apply_paper_theme() -> None:
    """Apply a consistent seaborn theme for publication figures (idempotent).

    Sets a white grid, the paper context, and the validated categorical palette
    so every figure in the package reads as one system. Safe to call repeatedly.
    """
    global _THEME_APPLIED
    if _THEME_APPLIED:
        return
    sns.set_theme(
        style="whitegrid",
        context="paper",
        palette=PALETTE,
        rc={
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "grid.alpha": 0.3,
        },
    )
    _THEME_APPLIED = True


# Apply the theme on import so any module that draws inherits it.
apply_paper_theme()


def save_figure(fig: Figure, output_path: str, *, dpi: int = 300) -> None:
    """Persist a figure to ``output_path`` and close it.

    Creates the parent directory, tightens the layout, writes at ``dpi`` with a
    tight bounding box, then closes the figure to free memory. Replaces the
    mkdir/tight_layout/savefig/close boilerplate that was repeated per plot.
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def load_json_data(file_path: str) -> Any:
    """Load JSON data from file (may be a dict, list, or scalar)."""
    with open(file_path, "r") as f:
        return json.load(f)
