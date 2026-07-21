"""Windowing and time-series statistics (pure data transforms)."""

from __future__ import annotations

from typing import Any, List, Dict
from datetime import datetime, timezone

import numpy as np
import pandas as pd


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


def steady_state_long_frame(
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
            samples = [float(v) for v in series.get("values", []) if v is not None]
        if len(samples) < 3:
            continue
        label = (
            series.get("interval_mode") or series.get("label") or f"Series {idx + 1}"
        )
        order.append(label)
        rows.extend({"mode": label, "value": v} for v in samples)
    return pd.DataFrame(rows), order


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
