"""Matplotlib figure builders for distribution charts (box / ECDF / violin)."""

from __future__ import annotations

from typing import Any, List, Dict

import matplotlib.pyplot as plt
import seaborn as sns

from .common import FIGSIZE_STD, PALETTE, save_figure
from .windowing import steady_state_samples, steady_state_long_frame


def create_steady_state_boxplot(
    series_list: List[Dict[str, Any]],
    title: str = "Steady-state distribution",
    output_path: str = "boxplot.png",
    y_axis_label: str = "Value",
    show_title: bool = True,
) -> None:
    """Box plot of the stabilized (plateau) samples, one box per mode.

    Warm-up and cool-down are trimmed via ``steady_state_samples`` so each box
    reflects only the post-stabilization region.
    """
    data: List[List[float]] = []
    labels: List[str] = []
    for idx, series in enumerate(series_list):
        samples = steady_state_samples(series.get("values", []))
        if len(samples) < 3:
            continue
        data.append(samples)
        labels.append(
            series.get("interval_mode") or series.get("label") or f"Series {idx + 1}"
        )
    if not data:
        print(f"No steady-state samples for box plot: {title}")
        return

    # Long mode names (e.g. "paytree_first_opt") collide at a fixed width once
    # there are more than a handful of boxes, so scale width with box count;
    # height follows width at 4:3 rather than a flat constant.
    fig_width = max(8, 1.8 * len(data))
    fig, ax = plt.subplots(figsize=(fig_width, fig_width * 3 / 4))
    positions = list(range(1, len(data) + 1))
    # Fliers are omitted: with the low variance typical of these metrics the IQR
    # is tiny, so most points render as fliers even though they aren't anomalies.
    # The companion ECDF/violin plots retain the full distribution and tails.
    ax.boxplot(data, positions=positions, showmeans=True, showfliers=False)
    ax.set_xticks(positions)
    # Show the median value under each mode label so it never overlaps the box.
    tick_labels = [
        f"{label}\nmed {sorted(samples)[len(samples) // 2]:.3g}"
        for label, samples in zip(labels, data)
    ]
    # Rotated + right-aligned so long mode names (e.g. "paytree_first_opt") don't
    # collide with their neighbors at a fixed horizontal layout.
    ax.set_xticklabels(tick_labels, rotation=30, ha="right")
    ax.set_ylabel(y_axis_label)
    if show_title:
        ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    save_figure(fig, output_path)
    print(f"Box plot saved to: {output_path}")


def create_precomputed_boxplot(
    stats: List[Dict[str, Any]],
    title: str = "Distribution",
    output_path: str = "boxplot.png",
    y_axis_label: str = "Value",
    show_title: bool = True,
) -> None:
    """Render a box plot from pre-computed per-box statistics (matplotlib ``bxp``).

    Each entry in ``stats`` must provide: ``label``, ``whislo``, ``q1``, ``med``,
    ``q3``, ``whishi`` (e.g. p5/p25/p50/p75/p95). Used for distributions that come
    from a Prometheus histogram, where individual samples are not available.
    """
    if not stats:
        print(f"No stats for box plot: {title}")
        return
    fig_width = max(8, 1.8 * len(stats))
    fig, ax = plt.subplots(figsize=(fig_width, fig_width * 3 / 4))
    ax.bxp(stats, showfliers=False)
    ax.set_xticks(list(range(1, len(stats) + 1)))
    # Rotated + right-aligned so long mode names (e.g. "paytree_first_opt") don't
    # collide with their neighbors at a fixed horizontal layout.
    ax.set_xticklabels(
        [f"{s.get('label', '')}\nmed {s['med']:.3g}" for s in stats],
        rotation=30,
        ha="right",
    )
    ax.set_ylabel(y_axis_label)
    if show_title:
        ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    save_figure(fig, output_path)
    print(f"Box plot saved to: {output_path}")


def create_bucket_ecdf(
    dists: List[Dict[str, Any]],
    title: str = "Distribution (ECDF)",
    output_path: str = "ecdf.png",
    value_label: str = "Value",
    show_title: bool = True,
) -> None:
    """Exact step ECDF drawn straight from Prometheus histogram buckets.

    Each entry provides ``label``, ``edges`` (the ``le`` upper bounds, ascending)
    and ``cum_fraction`` (cumulative count at each edge divided by the total
    count). Because the fraction is the bucket count itself -- not a
    reconstruction -- p50/p95/p99 read exactly off the curve. One step curve per
    mode; ``steps-post`` matches Prometheus ``le`` (<=) bucket semantics.
    """
    valid = [d for d in dists if d.get("edges") and d.get("cum_fraction")]
    if not valid:
        print(f"No bucket data for ECDF: {title}")
        return
    fig, ax = plt.subplots(figsize=FIGSIZE_STD)
    for idx, d in enumerate(valid):
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(
            d["edges"],
            d["cum_fraction"],
            drawstyle="steps-post",
            linewidth=2,
            color=color,
            label=d.get("label", f"Series {idx + 1}"),
        )
    ax.set_xlabel(value_label)
    ax.set_ylabel("Cumulative proportion")
    ax.set_ylim(0, 1.02)
    if show_title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", ncol=len(valid), frameon=False)
    save_figure(fig, output_path)
    print(f"ECDF plot saved to: {output_path}")


def create_ecdf_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Latency distribution (ECDF)",
    output_path: str = "ecdf.png",
    value_label: str = "Value",
    trim: bool = True,
    show_title: bool = True,
) -> None:
    """Empirical CDF of the samples, one curve per mode.

    An ECDF lets a reader read p50/p95/p99 straight off the curve and exposes the
    tail that a box plot hides. With ``trim`` (default) warm-up/cool-down are
    dropped via ``steady_state_samples`` so each curve reflects only the plateau;
    pass ``trim=False`` when the values are already a distribution.
    """
    df, order = steady_state_long_frame(series_list, trim=trim)
    if df.empty:
        print(f"No steady-state samples for ECDF: {title}")
        return
    fig, ax = plt.subplots(figsize=FIGSIZE_STD)
    sns.ecdfplot(data=df, x="value", hue="mode", hue_order=order, ax=ax)
    ax.set_xlabel(value_label)
    ax.set_ylabel("Cumulative proportion")
    if show_title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    # seaborn's hue legend builds its own Legend object directly rather than
    # labeling axes artists, so ax.get_legend_handles_labels() finds nothing --
    # a bare ax.legend() call here would silently replace it with an empty one.
    # Pull the handles/labels it already built and redraw with our placement.
    if ax.legend_ is not None:
        handles = ax.legend_.legend_handles
        labels = [t.get_text() for t in ax.legend_.get_texts()]
        ax.legend(
            handles=handles,
            labels=labels,
            loc="upper left",
            ncol=len(order),
            frameon=False,
        )
    save_figure(fig, output_path)
    print(f"ECDF plot saved to: {output_path}")


def create_violin_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Steady-state distribution",
    output_path: str = "violin.png",
    value_label: str = "Value",
    trim: bool = True,
    show_title: bool = True,
) -> None:
    """Violin plot of the samples, one violin per mode.

    Shows the full sample density (including bimodality) that a box plot flattens
    to five numbers. With ``trim`` (default) it drops warm-up/cool-down like
    ``create_steady_state_boxplot``; pass ``trim=False`` when the values are
    already a distribution (e.g. reconstructed from histogram buckets).
    """
    df, order = steady_state_long_frame(series_list, trim=trim)
    if df.empty:
        print(f"No steady-state samples for violin plot: {title}")
        return
    fig, ax = plt.subplots(figsize=FIGSIZE_STD)
    # hue=mode + legend=False colors each violin from the categorical palette;
    # this is the seaborn >=0.13 idiom (a bare ``palette`` is deprecated there).
    # cut=0 keeps the density within the observed data range: these metrics
    # (latency, CPU, network) are all >= 0, so the KDE must not bleed negative.
    sns.violinplot(
        data=df,
        x="mode",
        y="value",
        order=order,
        hue="mode",
        hue_order=order,
        legend=False,
        cut=0,
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel(value_label)
    if show_title:
        ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    save_figure(fig, output_path)
    print(f"Violin plot saved to: {output_path}")
