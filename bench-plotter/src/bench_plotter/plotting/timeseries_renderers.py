"""Matplotlib figure builders for timeseries charts."""

from __future__ import annotations

from typing import Any, List, Dict

import matplotlib.pyplot as plt

from bench_plotter.mode_style import MODE_MARKERS

from .common import FIGSIZE_WIDE, PALETTE, save_figure

# One marker per point, at a sparse stride: a marker on every raw Prometheus
# sample would be an unreadable smear, but the shape still needs to appear
# often enough to tell series apart without relying on color alone (this
# benchmark's convention -- see mode_style.MODE_MARKERS). Color + marker is
# the full identity encoding here -- there is only one dimension (series),
# so linestyle stays fixed rather than cycling too and double-encoding it.
_MARKER_EVERY = 15


def create_multi_line_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Time Series Comparison",
    output_path: str = "line_plot.png",
    y_axis_label: str = "Value",
    show_title: bool = True,
) -> None:
    """Plot the raw Prometheus points, one line per series (no extra smoothing)."""
    if not series_list:
        print("No series provided for multi-series plotting")
        return
    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE)
    max_value = 0.0
    drawn_count = 0
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

        ax.plot(
            plot_elapsed,
            plot_values,
            color=color,
            linewidth=2,
            marker=marker,
            markevery=_MARKER_EVERY,
            markersize=7,
            label=label,
        )
        max_value = max(max_value, max(valid_values))
        drawn_count += 1
    ax.set_xlabel("Time (s)", fontsize=20)
    ax.set_ylabel(y_axis_label, fontsize=20)
    ax.tick_params(axis="both", which="major", labelsize=17)
    ax.grid(True, alpha=0.3)
    # The legend lives above the axes -- this chart's series are raw time
    # series that can spike anywhere, including right at the top, and an
    # inside-axes legend once crowded a peak that reached the y-limit's
    # headroom. Capped at 3/row so it wraps instead of forcing every mode
    # into one wide row; the title's large pad reserves room for the (up to
    # two-row) legend between it and the axes, so neither ever overlaps the
    # other or the data. Font sizes here are the shared convention every
    # vs-TPS chart (sweep_renderers.create_sweep_line_plot /
    # create_identity_comparison_plot) matches too.
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.0),
        ncol=min(3, max(1, drawn_count)),
        fontsize=20,
        frameon=False,
    )
    if show_title:
        ax.set_title(title, fontsize=24, pad=135)
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    ax.set_xlim(left=0)
    save_figure(fig, output_path)
    print(f"Line plot saved to: {output_path}")
