"""Histogram plotting and processing utilities."""

from __future__ import annotations

from typing import Any, List, Dict, Tuple
import matplotlib.pyplot as plt
import numpy as np

from .common import save_figure


def histogram_to_samples(
    edges: List[float],
    cumulative: List[float],
    max_total: int = 5000,
) -> List[float]:
    """Reconstruct approximate samples from a cumulative histogram.

    ``edges`` are ascending ``le`` upper bounds and ``cumulative`` the aligned
    cumulative counts (or fractions). Per-bucket weights are differenced, then
    each bucket contributes samples spread uniformly across its ``(lower, upper]``
    span, in proportion to its weight, capped at ``max_total`` total.

    The result approximates the *shape* of the distribution (for a violin/KDE); it
    is NOT the original per-observation data, so any density drawn from it is an
    interpolation of the bucket counts, not measured samples.
    """
    if not edges or len(edges) != len(cumulative):
        return []
    lowers: List[float] = []
    weights: List[float] = []
    prev_edge = 0.0
    prev_cum = 0.0
    for edge, cum in zip(edges, cumulative):
        weights.append(max(0.0, float(cum) - prev_cum))
        lowers.append(prev_edge)
        prev_edge = float(edge)
        prev_cum = float(cum)
    total = sum(weights)
    if total <= 0:
        return []
    samples: List[float] = []
    for lower, upper, weight in zip(lowers, edges, weights):
        n = int(round(max_total * weight / total))
        if n <= 0:
            continue
        if n == 1 or upper <= lower:
            samples.append((lower + float(upper)) / 2.0)
            continue
        # Evenly spread inside the bucket, avoiding the exact edges.
        samples.extend(np.linspace(lower, float(upper), n + 2)[1:-1].tolist())
    return samples


def cumulative_to_per_bucket(
    bucket_labels: List[str],
    cumulative_values: List[float],
    drop_inf: bool = True,
) -> Tuple[List[str], List[float]]:
    """
    Convert sorted cumulative Prometheus bucket counts to per-bucket counts.

    Each per-bucket count is the difference from the previous cumulative value,
    clamped at zero: cumulative buckets can appear to decrease when a counter
    resets or samples arrive slightly out of order, and negative frequencies are
    never meaningful.

    Args:
        bucket_labels: Sorted bucket labels (ascending, "+Inf" last if present)
        cumulative_values: Cumulative counts aligned with ``bucket_labels``
        drop_inf: If True, drop a trailing "+Inf" bucket (the running total)

    Returns:
        Tuple of (labels, per_bucket_values)
    """
    labels = list(bucket_labels)
    per_bucket_values: List[float] = []
    for i, v in enumerate(cumulative_values):
        if i == 0:
            per_bucket_values.append(max(0.0, float(v)))
        else:
            per_bucket_values.append(
                max(0.0, float(v) - float(cumulative_values[i - 1]))
            )

    if drop_inf and labels and labels[-1] == "+Inf":
        labels = labels[:-1]
        per_bucket_values = per_bucket_values[:-1]

    return labels, per_bucket_values


def process_histogram_data(
    runs_data: List[Dict[str, Any]],
) -> tuple[List[str], List[float]]:
    """
    Process histogram data by aggregating bucket values.

    Args:
        runs_data: List of series data with 'le' labels in their structure

    Returns:
        Tuple of (bucket_labels, aggregated_values)
    """
    bucket_dict = {}

    # For each series (each bucket)
    for series in runs_data:
        values = series.get("values", [])
        if not values:
            continue

        # Get the last (most recent) value for this bucket
        last_value = values[-1] if values[-1] is not None else 0

        # The bucket label should be in the series data
        # For histogram_quantile results, we need to extract from the query result
        bucket_label = series.get("bucket_label", "unknown")
        bucket_dict[bucket_label] = float(last_value)

    # Sort buckets in a sensible order
    def sort_key(item: Tuple[str, float]) -> float:
        label = item[0]
        if label == "+Inf":
            return float("inf")
        try:
            return float(label)
        except ValueError:
            return float("inf")

    sorted_buckets = sorted(bucket_dict.items(), key=sort_key)

    if sorted_buckets:
        labels = [item[0] for item in sorted_buckets]
        # bucket_dict contains cumulative counts per Prometheus histogram semantics.
        # Convert cumulative counts to per-bucket (non-cumulative) counts by differencing.
        raw_values = [item[1] for item in sorted_buckets]
        return cumulative_to_per_bucket(labels, raw_values)

    return [], []


def is_histogram_query(expr: str, title: str, legend_format: str) -> bool:
    """
    Detect if a query is for histogram data (returns buckets, not a scalar).

    Args:
        expr: PromQL expression
        title: Panel title
        legend_format: Legend format string

    Returns:
        True if this appears to be a histogram query that returns bucket data
    """
    expr_lower = (expr or "").lower()

    # If query starts with histogram_quantile, it returns a scalar, not buckets
    if "histogram_quantile" in expr_lower:
        return False

    # Check title for histogram/distribution keywords (but not percentile/quantile)
    title_lower = title.lower()
    if (
        "quantile" in title_lower
        or "p99" in title_lower
        or "p95" in title_lower
        or "p50" in title_lower
    ):
        return False
    if "distribution" in title_lower or "histogram" in title_lower:
        return True

    # Common Prometheus histogram patterns: *_bucket metrics with 'by (le)' but NO histogram_quantile
    if "_bucket" in expr_lower and ("by (le)" in expr_lower or " by(le)" in expr_lower):
        return True

    return False


def create_histogram_plot(
    buckets: List[str],
    counts: List[float],
    title: str = "Distribution",
    output_path: str = "histogram.png",
) -> None:
    """
    Create a histogram bar plot from bucket data.

    Args:
        buckets: List of bucket labels (e.g., ['0.25', '0.5', '0.75', ...])
        counts: List of counts for each bucket
        title: Plot title
        output_path: Path to save the PNG file
    """
    if not buckets or not counts:
        print("No data provided for histogram")
        return

    # Create figure with better sizing
    fig, ax = plt.subplots(figsize=(14, 8))

    # Create color gradient based on value (low=green, high=red)
    max_count = max(counts) if counts else 1
    colors = []
    for count in counts:
        # Normalize count to 0-1
        normalized = count / max_count if max_count > 0 else 0
        # Color gradient: green (0) -> yellow -> orange -> red (1)
        if normalized < 0.33:
            # Green to yellow
            r = min(1.0, normalized * 3)
            g = 0.7
            b = 0.0
        elif normalized < 0.66:
            # Yellow to orange
            r = 1.0
            g = max(0.0, 1.0 - ((normalized - 0.33) * 1.5))
            b = 0.0
        else:
            # Orange to red
            r = 1.0
            g = max(0.0, 0.4 - ((normalized - 0.66) * 1.2))
            b = 0.0

        # Ensure values are within 0-1
        r = max(0.0, min(1.0, r))
        g = max(0.0, min(1.0, g))
        b = max(0.0, min(1.0, b))

        colors.append((r, g, b))

    # Create bar plot
    bars = ax.bar(
        range(len(buckets)), counts, color=colors, edgecolor="black", linewidth=0.5
    )

    # Add value labels on top of bars
    for i, (bar, count) in enumerate(zip(bars, counts)):
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(count)}" if count == int(count) else f"{count:.0f}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    # Set x-axis labels
    ax.set_xticks(range(len(buckets)))
    ax.set_xticklabels(buckets, rotation=0, ha="center")

    ax.set_xlabel("Latency Bucket (ms)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Frequency", fontsize=11, fontweight="bold")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_ylim(bottom=0)

    save_figure(fig, output_path)

    print(f"Histogram plot saved to: {output_path}")


def create_overlaid_histogram_plot(
    histogram_data: Dict[str, Tuple[List[str], List[float]]],
    title: str = "Distribution",
    output_path: str = "histogram_overlay.png",
) -> None:
    """
    Create an overlaid frequency distribution line plot from multiple modes.

    Args:
        histogram_data: Dict mapping mode name to (bucket_labels, per_bucket_values)
        title: Plot title
        output_path: Path to save the PNG file
    """
    if not histogram_data:
        print("No data provided for overlaid histogram")
        return

    modes = list(histogram_data.keys())
    if not modes:
        return

    fig, ax = plt.subplots(figsize=(20, 10))

    colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple"]
    # Different linestyles distinguish overlapping series without noisy markers
    linestyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]

    max_value = 0.0

    for idx, mode in enumerate(modes):
        buckets, values = histogram_data[mode]
        color = colors[idx % len(colors)]
        linestyle = linestyles[idx % len(linestyles)]

        # Use real float x-values so each mode only spans its own buckets.
        # This prevents artificial zeros at buckets the mode didn't measure.
        x_vals: List[float] = []
        y_vals: List[float] = []
        for bucket, value in zip(buckets, values):
            try:
                x_vals.append(float(bucket))
                y_vals.append(float(value))
            except (ValueError, TypeError):
                pass

        if not x_vals:
            continue

        max_value = max(max_value, max(y_vals))
        ax.plot(
            x_vals, y_vals, color=color, linewidth=2, linestyle=linestyle, label=mode
        )

    # Trim x-axis to where there is still significant frequency (>1% of global peak).
    # This removes the long empty tail without hiding real data.
    all_x: List[float] = []
    all_y: List[float] = []
    for mode in modes:
        buckets, values = histogram_data[mode]
        for b, v in zip(buckets, values):
            try:
                all_x.append(float(b))
                all_y.append(float(v))
            except (ValueError, TypeError):
                pass

    if all_x and all_y:
        threshold = max(all_y) * 0.01
        significant_x = [x for x, y in zip(all_x, all_y) if y >= threshold]
        x_right = max(significant_x) * 1.15 if significant_x else max(all_x)
        ax.set_xlim(left=0, right=x_right)

    ax.set_xlabel("Latency Bucket (ms)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Frequency", fontsize=14, fontweight="bold")
    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0, top=max_value * 1.1 if max_value > 0 else 1.0)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)

    save_figure(fig, output_path)

    print(f"Overlaid histogram plot saved to: {output_path}")
