"""Matplotlib figure builders for timeseries charts."""

from __future__ import annotations

from typing import Any, List, Dict

import matplotlib.pyplot as plt

from .common import save_figure
from .windowing import (
    calculate_windowed_averages,
    calculate_optimal_window_size,
    normalize_time_series_data,
)


def create_windowed_plot_multi(
    series_list: List[Dict[str, Any]],
    title: str = "Time Series Comparison",
    output_path: str = "windowed_plot.png",
    y_axis_label: str = "Value",
) -> None:
    """Create a multi-series windowed plot."""
    if not series_list:
        print("No series provided for multi-series plotting")
        return
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple"]
    linestyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]
    window_seconds_param = None
    max_value = 0.0
    for idx, series in enumerate(series_list):
        timestamps = series.get("timestamps", [])
        values = series.get("values", [])
        label = series.get("label")
        interval_mode = series.get("interval_mode")
        ws = series.get("window_seconds", None)
        if ws is None:
            ws = window_seconds_param
        if ws is None:
            try:
                ws = calculate_optimal_window_size(timestamps) if timestamps else None
            except Exception:
                ws = None
        if not label:
            label = interval_mode or f"Series {idx + 1}"
        if not timestamps or not values:
            continue

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            continue

        start_time = float(timestamps[0])
        color = colors[idx % len(colors)]
        linestyle = linestyles[idx % len(linestyles)]

        # Apply windowed averaging when a window size is available; fall back to
        # raw samples otherwise.
        plot_elapsed: List[float] = []
        plot_values: List[float] = []
        if ws is not None and float(ws) > 0:
            window_centers, window_averages = calculate_windowed_averages(
                timestamps, values, float(ws)
            )
            if window_centers:
                plot_elapsed = [
                    float(wc.timestamp()) - start_time for wc in window_centers
                ]
                plot_values = window_averages
        if not plot_elapsed:
            plot_elapsed = [float(ts) - start_time for ts in timestamps]
            plot_values = values

        ax.plot(
            plot_elapsed,
            plot_values,
            color=color,
            linewidth=2,
            linestyle=linestyle,
            label=label,
        )
        valid_plot_values = [v for v in plot_values if v is not None]
        if valid_plot_values:
            max_value = max(max_value, max(valid_plot_values))
    ax.set_xlabel("Time (s)", fontsize=14)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    ax.set_xlim(left=0)
    save_figure(fig, output_path)
    print(f"Windowed plot saved to: {output_path}")


def create_mean_std_plot(
    runs_data: List[Dict[str, Any]],
    title: str = "Benchmark Statistics",
    output_path: str = "benchmark_stats.png",
    num_points: int = 100,
    y_axis_label: str = "Value",
) -> None:
    """
    Create matplotlib plot showing mean and standard deviation.

    Args:
        runs_data: List of dictionaries containing timestamps and values for each run
        title: Plot title
        output_path: Path to save the PNG file
        num_points: Number of interpolation points for time series normalization
        y_axis_label: Label for y-axis (e.g., "Value (MiB)")
    """
    if not runs_data:
        print("No data provided for plotting")
        return

    # Normalize time series data
    normalized_df = normalize_time_series_data(runs_data, num_points=num_points)

    if normalized_df.empty:
        print("No valid data for plotting")
        return

    # Calculate statistics
    stats_df = (
        normalized_df.groupby("relative_time")["value"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )

    # Handle cases where std is NaN (single values)
    stats_df["std"] = stats_df["std"].fillna(0)

    # Create the plot
    fig = plt.figure(figsize=(12, 8))

    # Time as percentage
    time_percentages = stats_df["relative_time"] * 100
    mean_values = stats_df["mean"]
    std_values = stats_df["std"]

    # Upper and lower bounds
    upper_values = mean_values + std_values
    lower_values = mean_values - std_values

    # Plot mean line
    plt.plot(time_percentages, mean_values, "b-", linewidth=2, label="Mean")

    # Fill the area between mean ± std
    plt.fill_between(
        time_percentages,
        lower_values,
        upper_values,
        alpha=0.3,
        color="blue",
        label="Mean ± Std",
    )

    # Plot the bounds as dashed lines
    plt.plot(time_percentages, upper_values, "b--", alpha=0.5, linewidth=1)
    plt.plot(time_percentages, lower_values, "b--", alpha=0.5, linewidth=1)

    plt.xlabel("Time Progress (%)")
    plt.ylabel(y_axis_label)
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.ylim(bottom=0)

    save_figure(fig, output_path)

    print(f"Plot saved to: {output_path}")
