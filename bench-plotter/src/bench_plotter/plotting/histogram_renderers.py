"""Matplotlib figure builders for overlaid histogram charts."""

from __future__ import annotations

from typing import Dict, List, Tuple

import matplotlib.pyplot as plt

from .common import save_figure


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
