"""Time series calculations and plotting utilities."""

from __future__ import annotations

from typing import Any, List, Dict, Optional
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from datetime import datetime, timezone

from .common import PALETTE, save_figure


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
    # A non-positive window never advances current_start and would loop forever.
    if window_seconds <= 0:
        print(f"Invalid window_seconds ({window_seconds}); must be > 0")
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
        print(f"Auto-calculated window size: {window_seconds:.2f} seconds")
    else:
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
        label="Window Average",
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
    save_figure(fig, output_path)
    print(f"Windowed plot saved to: {output_path}")


def steady_state_samples(values: List[Any]) -> List[float]:
    """Return only the stabilized (plateau) samples of a series.

    The warm-up ramp and the cool-down drain are dropped by keeping the samples
    within +/-20% of the series median. This works when the plateau dominates the
    window (as for the vendor under sustained load): the median lands on the
    plateau, and the ramp/drain samples fall outside the band. Returns ``[]`` when
    there is too little data.
    """
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 4:
        return []
    ordered = sorted(vals)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return []
    return [v for v in vals if abs(v - median) <= 0.2 * median]


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


def create_precomputed_ecdf(
    stats: List[Dict[str, Any]],
    title: str = "Distribution (ECDF)",
    output_path: str = "ecdf.png",
    value_label: str = "Value",
) -> None:
    """Step ECDF drawn from pre-computed quantiles, one curve per mode.

    Companion to :func:`create_precomputed_boxplot` for Prometheus-histogram
    distributions where individual samples are unavailable. Each entry in
    ``stats`` must provide ``label`` plus ``whislo``/``q1``/``med``/``q3``/
    ``whishi`` at the p5/p25/p50/p75/p95 quantiles; the curve steps through those
    (value, cumulative-proportion) points so p50/p95 read straight off the axes.
    """
    if not stats:
        print(f"No stats for ECDF: {title}")
        return
    probs = [0.05, 0.25, 0.50, 0.75, 0.95]
    keys = ["whislo", "q1", "med", "q3", "whishi"]
    fig, ax = plt.subplots(figsize=(8, 6))
    for idx, s in enumerate(stats):
        xs = [s[k] for k in keys]
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(
            xs,
            probs,
            marker="o",
            markersize=5,
            linewidth=2,
            color=color,
            label=s.get("label", f"Series {idx + 1}"),
        )
    ax.set_xlabel(value_label, fontsize=14)
    ax.set_ylabel("Cumulative proportion", fontsize=14)
    ax.set_ylim(0, 1)
    ax.set_title(title, fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", which="major", labelsize=12)
    save_figure(fig, output_path)
    print(f"ECDF plot saved to: {output_path}")


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


def _steady_state_long_frame(
    series_list: List[Dict[str, Any]],
    trim: bool = True,
) -> tuple[pd.DataFrame, List[str]]:
    """Build a long-form (``mode``, ``value``) frame of samples per mode.

    Shared by the ECDF and violin plots. Returns the frame plus the mode order
    (first-seen). With ``trim`` (the default) warm-up/cool-down are dropped via
    ``steady_state_samples``, exactly like the box plot. Pass ``trim=False`` when
    the values are already a distribution (e.g. reconstructed from a histogram),
    where the tails must be kept rather than clipped to +/-20% of the median.
    """
    rows: List[Dict[str, Any]] = []
    order: List[str] = []
    for idx, series in enumerate(series_list):
        if trim:
            samples = steady_state_samples(series.get("values", []))
        else:
            samples = [
                float(v) for v in series.get("values", []) if v is not None
            ]
        if len(samples) < 3:
            continue
        label = (
            series.get("interval_mode") or series.get("label") or f"Series {idx + 1}"
        )
        order.append(label)
        rows.extend({"mode": label, "value": v} for v in samples)
    return pd.DataFrame(rows), order


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
    df, order = _steady_state_long_frame(series_list, trim=trim)
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
    df, order = _steady_state_long_frame(series_list, trim=trim)
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
