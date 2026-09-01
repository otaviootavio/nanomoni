"""Matplotlib figure builders for timeseries charts."""

from __future__ import annotations

from typing import Any, List, Dict, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from bench_plotter.mode_style import MODE_MARKERS

from .common import FIGSIZE_PRINT_TS, PALETTE, save_figure

# One marker per point, at a sparse stride: a marker on every raw Prometheus
# sample would be an unreadable smear, but the shape still needs to appear
# often enough to tell series apart without relying on color alone (this
# benchmark's convention -- see mode_style.MODE_MARKERS). Color + marker is
# the full identity encoding here -- there is only one dimension (series),
# so linestyle stays fixed rather than cycling too and double-encoding it.
_MARKER_EVERY = 15

# The only series a linear fit is meaningful for: modes with a known unbounded
# per-payment keyspace leak (see the PayTree merkle-node cleanup gap). Every
# other mode holds roughly flat, so fitting them too would add near-zero
# dashed lines and legend rows that dilute the two curves worth reading.
# paytree_second_opt shares first-opt's sparse merkle-node store (same
# cleanup gap) plus its own eagerly-stored full proof, so it leaks too.
_LINEAR_FIT_LABELS = frozenset(
    {"paytree_first_opt", "paytree_second_opt", "paytree_child_pair"}
)


def create_multi_line_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Time Series Comparison",
    output_path: str = "line_plot.png",
    y_axis_label: str = "Value",
    show_title: bool = True,
    show_linear_fit: bool = False,
    figsize: Optional[Tuple[float, float]] = None,
) -> None:
    """Plot the raw Prometheus points, one line per series (no extra smoothing).

    ``show_linear_fit`` overlays a least-squares ``y = m*t + n`` line (dashed,
    same color, no markers) for series in ``_LINEAR_FIT_LABELS`` only, with the
    slope written as a small in-axes text stack rather than a wider legend
    entry -- meant for charts expected to grow roughly linearly over the run
    (e.g. an unbounded Redis keyspace leak), not for charts like CPU/network
    that merely fluctuate.

    ``figsize`` defaults to ``FIGSIZE_PRINT_TS``; pass ``FIGSIZE_PRINT_TS_WIDE``
    (or another override) for a chart whose legend needs a wider axes to align
    with its right edge.
    """
    if not series_list:
        print("No series provided for multi-series plotting")
        return
    fig, ax = plt.subplots(figsize=figsize or FIGSIZE_PRINT_TS)
    max_value = 0.0
    drawn_count = 0
    fit_notes: List[Any] = []  # [(label, slope, color)] for the in-axes equation box
    for idx, series in enumerate(series_list):
        timestamps = series.get("timestamps", [])
        values = series.get("values", [])
        label = series.get("label")
        interval_mode = series.get("interval_mode")
        if not label:
            label = interval_mode or f"Series {idx + 1}"
        if not timestamps or not values:
            continue

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            continue

        start_time = float(timestamps[0])
        color = PALETTE[idx % len(PALETTE)]
        marker = MODE_MARKERS[idx % len(MODE_MARKERS)]

        plot_elapsed = [float(ts) - start_time for ts in timestamps]
        plot_values = values

        fit_m = fit_n = None
        fit_t: List[float] = []
        if show_linear_fit and label in _LINEAR_FIT_LABELS:
            fit_t = [t for t, v in zip(plot_elapsed, plot_values) if v is not None]
            fit_v = [v for v in plot_values if v is not None]
            if len(fit_t) >= 2:
                fit_m, fit_n = np.polyfit(fit_t, fit_v, 1)

        ax.plot(
            plot_elapsed,
            plot_values,
            color=color,
            linewidth=1.1,
            marker=marker,
            markevery=_MARKER_EVERY,
            markersize=3.5,
            label=label,
        )
        # Repeat-reduced series carry mean +/- sample-std bands (see
        # repeats.reduce_repeat_timeseries); draw them as a translucent fill
        # behind the mean line -- the timeseries analogue of the vs-TPS
        # error bars in create_sweep_line_plot.
        values_low = series.get("values_low")
        values_high = series.get("values_high")
        if (
            values_low is not None
            and values_high is not None
            and len(values_low) == len(plot_elapsed)
            and len(values_high) == len(plot_elapsed)
        ):
            ax.fill_between(
                plot_elapsed,
                values_low,
                values_high,
                color=color,
                alpha=0.15,
                linewidth=0,
            )
            band_highs = [float(v) for v in values_high if v is not None]
            if band_highs:
                max_value = max(max_value, max(band_highs))
        max_value = max(max_value, max(valid_values))
        drawn_count += 1

        if fit_m is not None:
            fit_line = fit_m * np.array(fit_t) + fit_n
            ax.plot(
                fit_t, fit_line, color=color, linewidth=1.0, linestyle="--", alpha=0.8
            )
            fit_notes.append((label, fit_m, color))
    ax.set_xlabel("Time (s)", fontsize=9)
    ax.set_ylabel(y_axis_label, fontsize=9)
    ax.tick_params(axis="both", which="major", labelsize=8)
    ax.grid(True, alpha=0.3)
    # Slopes render as a small in-axes text stack (top-left: low elapsed time,
    # so empty for the growing series this is used on) rather than folded into
    # the legend -- a long "(fit m=...)" suffix there widened the saved
    # bbox_inches="tight" canvas far past the narrow print-size axes, crushing
    # the actual plot into a sliver of the image.
    for row, (fit_label, fit_slope, fit_color) in enumerate(fit_notes):
        ax.text(
            0.03,
            0.97 - row * 0.09,
            f"{fit_label}: m={fit_slope:.4f}",
            transform=ax.transAxes,
            color=fit_color,
            fontsize=6.5,
            va="top",
            ha="left",
        )
    # The legend lives above the axes -- this chart's series are raw time
    # series that can spike anywhere, including right at the top, and an
    # inside-axes legend once crowded a peak that reached the y-limit's
    # headroom. Capped at 2/row at this print size (long mode names in a
    # 3rd column no longer fit an axes this narrow); the title's pad
    # reserves room for the (up to three-row) legend between it and the
    # axes, so neither ever overlaps the other or the data.
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.0),
        ncol=min(2, max(1, drawn_count)),
        fontsize=8,
        frameon=False,
    )
    if show_title:
        ax.set_title(title, fontsize=10, pad=55)
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    ax.set_xlim(left=0)
    save_figure(fig, output_path)
    print(f"Line plot saved to: {output_path}")
