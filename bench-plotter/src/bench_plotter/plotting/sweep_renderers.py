"""Matplotlib figure builders for TPS-sweep charts (metric vs TPS)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np

from .common import PALETTE, save_figure

_LINESTYLES = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]
_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]


def _aligned_error_bars(
    ys: Sequence[float],
    y_low: Optional[Sequence[Any]],
    y_high: Optional[Sequence[Any]],
) -> Optional[np.ndarray]:
    """Build matplotlib ``yerr`` shape (2, N) from absolute low/high bounds.

    Returns ``None`` when bounds are missing or misaligned. Negative distances
    (e.g. a noisy quantile above the centre) are clamped to 0.
    """
    if y_low is None or y_high is None:
        return None
    if len(y_low) != len(ys) or len(y_high) != len(ys):
        return None
    lower = []
    upper = []
    for y, lo, hi in zip(ys, y_low, y_high):
        if lo is None or hi is None:
            lower.append(0.0)
            upper.append(0.0)
            continue
        lower.append(max(0.0, float(y) - float(lo)))
        upper.append(max(0.0, float(hi) - float(y)))
    return np.array([lower, upper])


def create_sweep_line_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Metric vs TPS",
    output_path: str = "sweep_line.png",
    x_axis_label: str = "TPS",
    y_axis_label: str = "Value",
) -> None:
    """Plot one or more series of (x, y) points against TPS.

    Each entry in ``series_list`` is
    ``{"x_values": [...], "y_values": [...], "label": str}`` with optional
    ``color``, ``linestyle``, ``marker``, and absolute error bounds
    ``y_low`` / ``y_high`` (drawn as asymmetric error bars). Missing style keys
    fall back to the index-based palette / linestyle / marker cycle.
    """
    if not series_list:
        print("No series provided for sweep line plot")
        return

    fig, ax = plt.subplots(figsize=(12, 8))
    max_value = 0.0
    any_drawn = False

    for idx, series in enumerate(series_list):
        x_values = series.get("x_values", [])
        y_values = series.get("y_values", [])
        label = series.get("label") or f"Series {idx + 1}"
        if not x_values or not y_values or len(x_values) != len(y_values):
            continue

        y_low = series.get("y_low")
        y_high = series.get("y_high")
        triples = []
        for i, (x, y) in enumerate(zip(x_values, y_values)):
            if x is None or y is None:
                continue
            lo = y_low[i] if y_low is not None and i < len(y_low) else None
            hi = y_high[i] if y_high is not None and i < len(y_high) else None
            triples.append((float(x), float(y), lo, hi))
        if not triples:
            continue
        triples.sort(key=lambda t: t[0])
        xs = [t[0] for t in triples]
        ys = [t[1] for t in triples]
        lows = [t[2] for t in triples]
        highs = [t[3] for t in triples]

        color = series.get("color") or PALETTE[idx % len(PALETTE)]
        linestyle = series.get("linestyle") or _LINESTYLES[idx % len(_LINESTYLES)]
        marker = series.get("marker") or _MARKERS[idx % len(_MARKERS)]
        # Only draw error bars when the series explicitly provided bounds.
        yerr = (
            _aligned_error_bars(ys, lows, highs)
            if y_low is not None and y_high is not None
            else None
        )

        if yerr is not None:
            ax.errorbar(
                xs,
                ys,
                yerr=yerr,
                color=color,
                linewidth=2,
                linestyle=linestyle,
                marker=marker,
                markersize=7,
                capsize=4,
                elinewidth=1.5,
                label=label,
            )
            bound_highs = [float(h) for h in highs if h is not None]
            max_value = max(max_value, max(ys), *(bound_highs or [0.0]))
        else:
            ax.plot(
                xs,
                ys,
                color=color,
                linewidth=2,
                linestyle=linestyle,
                marker=marker,
                markersize=7,
                label=label,
            )
            max_value = max(max_value, max(ys))
        any_drawn = True

    if not any_drawn:
        plt.close(fig)
        print("No drawable points for sweep line plot")
        return

    ax.set_xlabel(x_axis_label, fontsize=14)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    save_figure(fig, output_path)
    print(f"Sweep line plot saved to: {output_path}")
