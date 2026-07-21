"""Matplotlib figure builders for distribution charts (box / ECDF / violin)."""

from __future__ import annotations

from typing import Any, List, Dict

import matplotlib.pyplot as plt
import seaborn as sns

from .common import PALETTE, save_figure
from .windowing import steady_state_samples, steady_state_long_frame


def create_steady_state_boxplot(
    series_list: List[Dict[str, Any]],
    title: str = "Steady-state distribution",
    output_path: str = "boxplot.png",
    y_axis_label: str = "Value",
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

    fig, ax = plt.subplots(figsize=(8, 6))
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
    ax.set_xticklabels(tick_labels)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"Box plot saved to: {output_path}")


def create_precomputed_boxplot(
    stats: List[Dict[str, Any]],
    title: str = "Distribution",
    output_path: str = "boxplot.png",
    y_axis_label: str = "Value",
) -> None:
    """Render a box plot from pre-computed per-box statistics (matplotlib ``bxp``).

    Each entry in ``stats`` must provide: ``label``, ``whislo``, ``q1``, ``med``,
    ``q3``, ``whishi`` (e.g. p5/p25/p50/p75/p95). Used for distributions that come
    from a Prometheus histogram, where individual samples are not available.
    """
    if not stats:
        print(f"No stats for box plot: {title}")
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bxp(stats, showfliers=False)
    ax.set_xticks(list(range(1, len(stats) + 1)))
    ax.set_xticklabels([f"{s.get('label', '')}\nmed {s['med']:.3g}" for s in stats])
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"Box plot saved to: {output_path}")


def create_bucket_ecdf(
    dists: List[Dict[str, Any]],
    title: str = "Distribution (ECDF)",
    output_path: str = "ecdf.png",
    value_label: str = "Value",
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
    fig, ax = plt.subplots(figsize=(8, 6))
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
    ax.set_xlabel(value_label, fontsize=14)
    ax.set_ylabel("Cumulative proportion", fontsize=14)
    ax.set_ylim(0, 1.02)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"ECDF plot saved to: {output_path}")


def create_ecdf_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Latency distribution (ECDF)",
    output_path: str = "ecdf.png",
    value_label: str = "Value",
    trim: bool = True,
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
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.ecdfplot(data=df, x="value", hue="mode", hue_order=order, ax=ax)
    ax.set_xlabel(value_label, fontsize=14)
    ax.set_ylabel("Cumulative proportion", fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"ECDF plot saved to: {output_path}")


def create_violin_plot(
    series_list: List[Dict[str, Any]],
    title: str = "Steady-state distribution",
    output_path: str = "violin.png",
    value_label: str = "Value",
    trim: bool = True,
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
    fig, ax = plt.subplots(figsize=(8, 6))
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
    ax.set_ylabel(value_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"Violin plot saved to: {output_path}")
