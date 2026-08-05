"""Matplotlib figure builders for TPS-sweep charts and tables (metric vs TPS)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

from .common import PALETTE, save_figure
from .table_renderer import render_table_figure, write_table_csv

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


def create_identity_comparison_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Achieved vs Target",
    output_path: str = "identity_comparison.png",
    x_axis_label: str = "Target",
    y_axis_label: str = "Achieved",
    identity_label: str = "y = x (ideal)",
) -> None:
    """Plot achieved-vs-target series against the ``y = x`` identity line.

    Purpose-built for reading a saturation curve, so the geometry carries the
    meaning: both axes get one shared base-2 log scale, identical limits, and
    identical ticks, with equal aspect. The identity line therefore runs at a
    true 45 degrees and vertical distance below it *is* the shortfall -- on
    mismatched axes a client that fell 3x short can look like it tracked the
    target. The log scale is what makes a doubling sweep legible: on a linear
    axis every point below 256 crowds into the left margin.

    Each entry in ``series_list`` is
    ``{"x_values": [...], "y_values": [...], "label": str}`` with optional
    ``color`` and ``marker``. The identity line is drawn by this function, so
    callers pass only measured series.
    """
    if not series_list:
        print("No series provided for identity comparison plot")
        return

    # Both scales are logarithmic, so non-positive points cannot be drawn at all.
    # Drop them here (rather than letting matplotlib silently clip) and keep the
    # surviving pairs per series.
    cleaned: List[Dict[str, Any]] = []
    all_values: List[float] = []
    all_x: List[float] = []
    for idx, series in enumerate(series_list):
        pairs = [
            (float(x), float(y))
            for x, y in zip(series.get("x_values", []), series.get("y_values", []))
            if x is not None and y is not None and float(x) > 0 and float(y) > 0
        ]
        if not pairs:
            continue
        pairs.sort(key=lambda p: p[0])
        cleaned.append({**series, "_pairs": pairs, "_idx": idx})
        all_x.extend(p[0] for p in pairs)
        all_values.extend(p[0] for p in pairs)
        all_values.extend(p[1] for p in pairs)

    if not cleaned:
        print("No drawable points for identity comparison plot")
        return

    # One padded range shared by both axes; multiplicative padding because the
    # axes are logarithmic.
    lo = min(all_values) / 1.4
    hi = max(all_values) * 1.4

    fig, ax = plt.subplots(figsize=(9, 9))

    # Identity line first so the measured series draw on top of it.
    ax.plot(
        [lo, hi],
        [lo, hi],
        color="#6b7280",
        linewidth=1.8,
        linestyle="--",
        zorder=1,
        label=identity_label,
    )

    for series in cleaned:
        pairs = series["_pairs"]
        idx = series["_idx"]
        ax.plot(
            [p[0] for p in pairs],
            [p[1] for p in pairs],
            color=series.get("color") or PALETTE[idx % len(PALETTE)],
            linewidth=2,
            linestyle="-",
            marker=series.get("marker") or _MARKERS[idx % len(_MARKERS)],
            markersize=8,
            zorder=2,
            label=series.get("label") or f"Series {idx + 1}",
        )

    for axis_setter, tick_setter in (
        (ax.set_xscale, ax.set_xticks),
        (ax.set_yscale, ax.set_yticks),
    ):
        axis_setter("log", base=2)
        # Tick at the swept targets on *both* axes: shared gridlines are what let
        # a reader check a point against the identity line by eye.
        tick_setter(sorted(set(all_x)))
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    # Equal aspect on matched log scales renders y = x at a true 45 degrees.
    ax.set_aspect("equal")
    ax.minorticks_off()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:g}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:g}"))

    ax.set_xlabel(x_axis_label, fontsize=14)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3, which="major")
    ax.legend(fontsize=12, loc="upper left")
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"Identity comparison plot saved to: {output_path}")


_MISSING_CELL = "-"


def _format_cell(tps: float, achieved: Optional[float]) -> str:
    """Real TPS with the percentage of target achieved in parentheses, or a placeholder.

    100% means the run hit its target exactly; below 100% is a shortfall and
    above 100% is an overshoot (typically sampling noise around an on-target run).
    """
    if achieved is None:
        return _MISSING_CELL
    pct = achieved / tps * 100 if tps else 0.0
    return f"{achieved:.1f} ({pct:.1f}%)"


def create_delta_table(
    tps_values: Sequence[float],
    modes: Sequence[str],
    achieved: Sequence[Sequence[Optional[float]]],
    title: str = "Real TPS by target and protocol (% = of target achieved)",
    output_path: str = "delta_table.png",
    row_header: str = "Target TPS",
) -> None:
    """Render a target-TPS x protocol grid of real TPS as a CSV and a table PNG.

    ``achieved[row][col]`` pairs with ``tps_values[row]`` and ``modes[col]``; a
    ``None`` cell renders as a placeholder rather than a misleading 0. Written
    alongside the chart because the chart shows *where* a protocol stops keeping
    up while this gives the magnitude at each step.
    """
    if not tps_values or not modes:
        print("No data for delta table")
        return

    col_labels = [row_header] + list(modes)
    cell_text = [
        [f"{tps:g}"] + [_format_cell(tps, a) for a in row]
        for tps, row in zip(tps_values, achieved)
    ]

    csv_path = write_table_csv(col_labels, cell_text, output_path)
    render_table_figure(
        col_labels, cell_text, title, output_path, bold_first_column=True
    )
    print(f"Delta table saved to: {output_path} (data: {csv_path})")
