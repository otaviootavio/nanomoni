"""Time series calculations and plotting utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Dict, Optional
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timezone


def calculate_sampling_frequency(timestamps: List[float]) -> float:
    """Calculate the sampling frequency from timestamps."""
    if len(timestamps) < 2:
        return 1.0
    sorted_timestamps = sorted(timestamps)
    intervals = []
    for i in range(1, len(sorted_timestamps)):
        interval = sorted_timestamps[i] - sorted_timestamps[i - 1]
        if interval > 0:
            intervals.append(interval)
    if not intervals:
        return 1.0
    try:
        return float(np.median(intervals))
    except Exception:
        return float(sum(intervals) / len(intervals))


def calculate_windowed_averages(
    timestamps: List[float],
    values: List[float],
    window_seconds: float = 5,
) -> tuple[List[datetime], List[float]]:
    """Calculate windowed averages for time series data."""
    if not timestamps or not values or len(timestamps) != len(values):
        return [], []

    df = pd.DataFrame({"timestamp": timestamps, "value": values})
    df = df.dropna(subset=["value"])
    if len(df) < 2:
        return [], []
    df = df.sort_values("timestamp")
    start_time = df["timestamp"].min()
    end_time = df["timestamp"].max()
    window_centers = []
    window_averages = []
    current_start = start_time
    while current_start < end_time:
        current_end = min(current_start + window_seconds, end_time)
        window_center = current_start + (current_end - current_start) / 2
        is_last = current_end >= end_time
        if is_last:
            window_data = df[
                (df["timestamp"] >= current_start) & (df["timestamp"] <= current_end)
            ]
        else:
            window_data = df[
                (df["timestamp"] >= current_start) & (df["timestamp"] < current_end)
            ]
        if not window_data.empty:
            window_avg = window_data["value"].mean()
            window_centers.append(
                datetime.fromtimestamp(window_center, tz=timezone.utc)
            )
            window_averages.append(window_avg)
        current_start = current_start + window_seconds
    return window_centers, window_averages


def calculate_optimal_window_size(
    timestamps: List[float], min_window_seconds: int = 1, multiplier: float = 2.0
) -> float:
    """Calculate optimal window size as double the sampling frequency."""
    if not timestamps or len(timestamps) < 2:
        return float(min_window_seconds)
    sampling = calculate_sampling_frequency(timestamps)
    try:
        window = float(sampling) * float(multiplier)
    except Exception:
        window = float(min_window_seconds)
    if window < min_window_seconds:
        return float(min_window_seconds)
    return float(window)


def create_windowed_plot(
    timestamps: List[float],
    values: List[float],
    title: str = "Time Series with Windowed Averages",
    output_path: str = "windowed_plot.png",
    window_seconds: Optional[float] = None,
    y_axis_label: str = "Value",
) -> None:
    """Create a plot with windowed averages for single interval data."""
    if not timestamps or not values:
        print("No data provided for plotting")
        return
    if window_seconds is None:
        window_seconds = calculate_optimal_window_size(timestamps)
        formatted_window = f"{window_seconds:.2f}".rstrip("0").rstrip(".")
        print(f"Auto-calculated window size: {formatted_window} seconds")
    else:
        formatted_window = f"{float(window_seconds):.2f}".rstrip("0").rstrip(".")
        print(f"Using specified window size: {window_seconds} seconds")
    window_centers, window_averages = calculate_windowed_averages(
        timestamps, values, window_seconds
    )
    if not window_centers:
        print("No valid windowed data for plotting")
        return
    start_time = float(timestamps[0])
    elapsed = [float(ts) - start_time for ts in timestamps]
    elapsed_centers = [float(wc.timestamp()) - start_time for wc in window_centers]
    fig, ax = plt.subplots(figsize=(12, 8))
    sample_rate = max(1, len(elapsed) // 1000)
    sample_elapsed = [elapsed[i] for i in range(len(elapsed)) if i % sample_rate == 0]
    sample_values = [values[i] for i in range(len(values)) if i % sample_rate == 0]
    ax.scatter(sample_elapsed, sample_values, alpha=0.5, s=20, color="gray", marker="o")
    ax.plot(
        elapsed_centers,
        window_averages,
        "b-",
        linewidth=2,
        label=f"{formatted_window}s Window Average",
    )
    ax.set_xlabel("Time (s)", fontsize=14)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    max_value = (
        max(sample_values + window_averages) if sample_values or window_averages else 0
    )
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    ax.set_xlim(left=0)
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Windowed plot saved to: {output_path}")


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
        formatted_window = None
        if ws is not None:
            formatted_window = f"{float(ws):.2f}".rstrip("0").rstrip(".")
        if not label:
            label = interval_mode or f"Series {idx + 1}"
        if formatted_window:
            label = f"{label} ({formatted_window}s window)"
        if not timestamps or not values:
            continue

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            continue

        start_time = float(timestamps[0])
        elapsed = [float(ts) - start_time for ts in timestamps]
        color = colors[idx % len(colors)]
        linestyle = linestyles[idx % len(linestyles)]
        ax.plot(
            elapsed, values, color=color, linewidth=2, linestyle=linestyle, label=label
        )
        max_value = max(max_value, max(valid_values))
    ax.set_xlabel("Time (s)", fontsize=14)
    ax.set_ylabel(y_axis_label, fontsize=14)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    top_limit = 1.0 if max_value <= 0 else max_value * 1.1
    ax.set_ylim(bottom=0, top=top_limit)
    ax.set_xlim(left=0)
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Windowed plot saved to: {output_path}")


def normalize_time_series_data(
    runs_data: List[Dict[str, Any]], num_points: int = 100
) -> pd.DataFrame:
    """
    Normalize multiple time series runs to a common time axis.

    Args:
        runs_data: List of dictionaries containing timestamps and values for each run
        num_points: Number of points to interpolate to

    Returns:
        DataFrame with normalized time series (0.0 to 1.0) and interpolated values
    """
    if not runs_data:
        return pd.DataFrame()

    normalized_runs: List[pd.DataFrame] = []

    for run_data in runs_data:
        timestamps = run_data.get("timestamps", [])
        values = run_data.get("values", [])

        if len(timestamps) == 0 or len(values) == 0:
            continue

        # Convert to relative time (0.0 to 1.0)
        start_time = timestamps[0]
        end_time = timestamps[-1]
        duration = end_time - start_time

        if duration <= 0:
            continue

        relative_times = [(ts - start_time) / duration for ts in timestamps]

        # Create DataFrame for this run
        df_run = pd.DataFrame({"relative_time": relative_times, "value": values})

        # Remove NaN values
        df_run = df_run.dropna(subset=["value"])

        if len(df_run) < 2:
            continue

        # Interpolate to standard number of points
        new_times = np.linspace(0, 1, num_points)
        df_interpolated = pd.DataFrame({"relative_time": new_times})

        # Interpolate values with error handling
        try:
            df_interpolated["value"] = np.interp(
                new_times, df_run["relative_time"], df_run["value"]
            )
        except (TypeError, ValueError) as e:
            print(f"Interpolation error for run: {e}")
            continue

        df_interpolated["run_id"] = len(normalized_runs)
        normalized_runs.append(df_interpolated)

    if not normalized_runs:
        return pd.DataFrame()

    return pd.concat(normalized_runs, ignore_index=True)


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
    plt.figure(figsize=(12, 8))

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

    # Create output directory if it doesn't exist
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the plot
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Plot saved to: {output_path}")
