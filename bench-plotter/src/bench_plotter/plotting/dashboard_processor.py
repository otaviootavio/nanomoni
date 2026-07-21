"""Dashboard processing logic and utilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, List, Dict
import asyncio

from .common import load_json_data
from .time_series import (
    create_windowed_plot,
    create_windowed_plot_multi,
    create_steady_state_boxplot,
    create_ecdf_plot,
    create_violin_plot,
    create_mean_std_plot,
    calculate_optimal_window_size,
)
from .histograms import (
    is_histogram_query,
    create_overlaid_histogram_plot,
    cumulative_to_per_bucket,
)
from .query_utils import sanitize_query


def extract_unit_from_title(title: str) -> str:
    """
    Extract unit from title for y-axis label.

    Args:
        title: Plot title (e.g., "Issuer Memory Usage (MiB)")

    Returns:
        Y-axis label with unit (e.g., "Value (MiB)")
    """
    # Look for pattern like "(MiB)", "(Cores)", "(KiB/s)", etc.
    match = re.search(r"\(([^)]+)\)", title)
    if match:
        unit = match.group(1)
        return f"Value ({unit})"
    return "Value"


def get_dashboard_panels(
    panels_spec: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """
    Get dashboard panels from specification or load from dashboard_queries module.

    Args:
        panels_spec: Optional panel specification (if None, loads from dashboard_queries)

    Returns:
        List of panel dictionaries
    """
    if panels_spec is not None:
        return panels_spec

    # Only fall back on an actual import failure of the canonical module. Config
    # or execution errors raised by get_dashboard_panels itself must propagate
    # rather than being masked by the legacy fallback.
    try:
        from bench_plotter.dashboard_queries import (
            get_dashboard_panels as _load_panels,
        )
    except ImportError:
        try:
            from dashboard_queries import (  # type: ignore[import-not-found]
                get_dashboard_panels as _load_panels_legacy,
            )
        except ImportError:
            print(
                "Error: dashboard_queries.py not found. Please create it from your dashboard configuration."
            )
            return []
        return _load_panels_legacy()

    return _load_panels()


def determine_interval_type(
    test_intervals: List[Dict[str, Any]],
) -> tuple[bool, Dict[str, List[Dict[str, Any]]]]:
    """
    Determine if intervals are single or multiple, and group by mode.

    Args:
        test_intervals: List of test interval dictionaries

    Returns:
        Tuple of (is_single_interval, modes_dict)
    """
    is_single_interval = len(test_intervals) == 1
    modes: Dict[str, List[Dict[str, Any]]] = {}

    if not is_single_interval:
        # Group intervals by mode
        for interval in test_intervals:
            mode = interval.get("mode", "unknown")
            if mode not in modes:
                modes[mode] = []
            modes[mode].append(interval)

        # Check if all intervals have the same mode
        if len(modes) == 1:
            # All intervals have same mode - use statistical analysis
            print(
                f"Multiple intervals detected ({len(test_intervals)}) with same mode, using statistical analysis"
            )
            is_single_interval = False
        else:
            # Different modes - treat each interval individually
            print(
                f"Multiple intervals detected ({len(test_intervals)}) with different modes: {list(modes.keys())}"
            )
            print("Treating each interval individually with windowed averaging")
            is_single_interval = True
    else:
        print(
            "Single interval detected, using automatic windowed averaging (2x sampling frequency)"
        )

    return is_single_interval, modes


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be safe for use as a filename.

    Args:
        name: String to sanitize

    Returns:
        Sanitized string safe for filenames
    """
    return (
        name.lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
        .replace("__", "_")
        .strip("_")
    )


def fetch_prometheus_data(
    expr: str,
    test_intervals: List[Dict[str, Any]],
    output_dir: str,
    panel_title: str,
    legend_format: str,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Fetch data from Prometheus for all test intervals.

    Args:
        expr: PromQL expression
        test_intervals: List of test interval dictionaries
        output_dir: Directory to save plots
        panel_title: Title of the panel
        legend_format: Legend format string

    Returns:
        Tuple of (runs_data, failed_fetches)
    """
    from bench_plotter.prometheus_fetch import (
        query_range,
        matrix_to_per_series_charts,
    )

    runs_data = []
    failed_fetches = []

    for interval_idx, interval in enumerate(test_intervals):
        timestamps = interval.get("prometheus_timestamps", {}) or {}
        start_ms = timestamps.get("start_ms")
        finish_ms = timestamps.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        start_time = start_ms / 1000
        end_time = finish_ms / 1000

        try:
            result = asyncio.run(
                query_range(
                    query=sanitize_query(expr),
                    start_unix=start_time,
                    end_unix=end_time,
                )
            )

            payload_result = (
                result.get("data", {}).get("result", [])
                if isinstance(result, dict)
                else []
            )

            if not payload_result:
                try:
                    logs_dir = Path(output_dir) / "logs"
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = panel_title.lower().replace(" ", "_")[:40]
                    fname = logs_dir / f"no_data_{safe_name}_{legend_format[:40]}.json"
                    with open(fname, "w") as lf:
                        json.dump({"query": expr, "result": result}, lf, default=str)
                except Exception:
                    pass

            charts = matrix_to_per_series_charts(payload_result)

            for chart in charts:
                runs_data.append(
                    {
                        "timestamps": chart["timestamps"],
                        "values": chart["data"],
                        "subtitle": chart.get("subtitle", ""),
                        "metric_name": chart.get("metric_name", ""),
                        "interval_mode": interval.get(
                            "mode", f"interval_{interval_idx + 1}"
                        ),
                    }
                )

        except Exception as e:
            error_msg = f"Error fetching data for interval {start_time}-{end_time}: {e}"
            print(error_msg)
            failed_fetches.append(
                {
                    "panel": panel_title,
                    "legend": legend_format,
                    "query": expr,
                    "interval": f"{start_time}-{end_time}",
                    "error": str(e),
                }
            )
            continue

    return runs_data, failed_fetches


def process_histogram_data_for_intervals(
    expr: str,
    test_intervals: List[Dict[str, Any]],
) -> Dict[str, tuple[List[str], List[float]]]:
    """
    Process histogram data for all intervals.

    Args:
        expr: PromQL expression
        test_intervals: List of test interval dictionaries

    Returns:
        Dictionary mapping mode to (bucket_labels, per_bucket_values)
    """
    from bench_plotter.prometheus_fetch import query_range, instant_query

    all_histogram_data = {}

    for interval_idx, interval in enumerate(test_intervals):
        timestamps = interval.get("prometheus_timestamps", {}) or {}
        start_ms = timestamps.get("start_ms")
        finish_ms = timestamps.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        start_time = start_ms / 1000
        end_time = finish_ms / 1000

        interval_mode = interval.get("mode", f"interval_{interval_idx + 1}")

        try:
            # Try instant query first, evaluated at the end of the benchmark
            # interval so we read the historical cumulative buckets rather than
            # Prometheus's current state.
            result = asyncio.run(instant_query(query=expr, time=end_time))

            vector_result = result.get("data", {}).get("result", [])

            # If instant query returns no results, try query_range
            if not vector_result:
                result = asyncio.run(
                    query_range(
                        query=expr,
                        start_unix=start_time,
                        end_unix=end_time,
                        step="60s",  # Use 60s step for histogram data
                    )
                )

                matrix_result = result.get("data", {}).get("result", [])

                # For query_range, use the last value from each series
                vector_result = []
                for item in matrix_result:
                    metric = item.get("metric", {})
                    values = item.get("values", [])
                    if values:
                        last_value = values[-1]
                        if (
                            last_value
                            and len(last_value) >= 2
                            and last_value[1] != "NaN"
                        ):
                            vector_result.append(
                                {"metric": metric, "value": last_value}
                            )

            bucket_data = {}
            for item in vector_result:
                metric = item.get("metric", {})
                le_value = metric.get("le", "unknown")
                value = item.get("value", [])

                if value and len(value) >= 2:
                    if value[1] != "NaN":
                        bucket_data[le_value] = float(value[1])

            def sort_key(item: tuple[Any, Any]) -> float:
                try:
                    return float(item[0])
                except (ValueError, TypeError):
                    return float("inf")

            sorted_buckets = sorted(bucket_data.items(), key=sort_key)

            if sorted_buckets:
                bucket_labels = [item[0] for item in sorted_buckets]
                raw_values = [item[1] for item in sorted_buckets]
                bucket_labels, per_bucket_values = cumulative_to_per_bucket(
                    bucket_labels, raw_values
                )
                all_histogram_data[interval_mode] = (bucket_labels, per_bucket_values)

        except Exception as e:
            print(f"Error processing histogram for interval {interval_mode}: {e}")
            continue

    return all_histogram_data


def extract_payment_mode_from_expr(expr: str) -> str:
    """Derive the payment mode name from a PromQL expression metric prefix."""
    expr_lower = expr.lower()
    if "paytree_" in expr_lower:
        return "paytree"
    if "payword_" in expr_lower:
        return "payword"
    return "signature"


def is_tps_panel(panel_title: str, legend_format: str, expr: str) -> bool:
    """
    Detect if a panel is TPS-related.

    Args:
        panel_title: Panel title
        legend_format: Legend format string
        expr: PromQL expression

    Returns:
        True if this appears to be a TPS panel
    """
    panel_title_lower = (panel_title or "").lower()
    legend_format_lower = (legend_format or "").lower()
    expr_lower = (expr or "").lower()

    # Exclude frequency distribution panels (these are histograms)
    if (
        "frequency distribution" in panel_title_lower
        or "distribution" in panel_title_lower
    ):
        return False

    return (
        panel_title_lower.find("tps") != -1
        or legend_format_lower.find("tps") != -1
        or expr_lower.find("tps") != -1
        or panel_title_lower.find("duration") != -1
        or panel_title_lower.find("quantile") != -1
        or panel_title_lower.find("payment") != -1
    )


def _plot_overlaid_series(
    runs_data: List[Dict[str, Any]],
    panel_title: str,
    legend_format: str,
    section_dir: Path,
    safe_panel_title: str,
    safe_legend: str,
    output_path: str | None = None,
    plot_title: str | None = None,
) -> None:
    """
    Build one overlaid multi-series windowed plot from ``runs_data``.

    Each series is labelled by its interval mode and given an auto-calculated
    window size. Series that are entirely zero are dropped unless every series
    is zero (in which case all are kept so the plot is not empty).

    Args:
        runs_data: List of series data
        panel_title: Panel title
        legend_format: Legend format string
        section_dir: Directory for the section
        safe_panel_title: Sanitized panel title for filename
        safe_legend: Sanitized legend for filename
        output_path: Optional output path (if None, generates from safe_panel_title and safe_legend)
        plot_title: Optional plot title (if None, generates from panel_title and legend_format)
    """
    temp_series = []
    for series_data in runs_data:
        interval_mode = series_data.get("interval_mode", "unknown")
        label = interval_mode
        timestamps = series_data.get("timestamps", [])
        values = series_data.get("values", [])
        try:
            ws = calculate_optimal_window_size(timestamps) if timestamps else None
        except Exception:
            ws = None

        temp_series.append(
            {
                "timestamps": timestamps,
                "values": values,
                "label": label,
                "window_seconds": ws,
            }
        )

    any_nonzero = any(
        any((v is not None and float(v) != 0) for v in s.get("values", []))
        for s in temp_series
    )

    if any_nonzero:
        series_list = [
            s
            for s in temp_series
            if any((v is not None and float(v) != 0) for v in s.get("values", []))
        ]
    else:
        series_list = temp_series

    if output_path is None:
        output_path = str(section_dir / f"{safe_panel_title}_{safe_legend}.png")
    if plot_title is None:
        plot_title = f"{panel_title} - {legend_format}"

    # Extract unit from title for y-axis label
    y_axis_label = extract_unit_from_title(plot_title)

    create_windowed_plot_multi(
        series_list=series_list,
        title=plot_title,
        output_path=str(output_path),
        y_axis_label=y_axis_label,
    )


def create_tps_plot(
    runs_data: List[Dict[str, Any]],
    panel_title: str,
    legend_format: str,
    section_dir: Path,
    safe_panel_title: str,
    safe_legend: str,
    output_path: str | None = None,
    plot_title: str | None = None,
) -> None:
    """Create a TPS plot with overlaid series (see ``_plot_overlaid_series``)."""
    _plot_overlaid_series(
        runs_data,
        panel_title,
        legend_format,
        section_dir,
        safe_panel_title,
        safe_legend,
        output_path,
        plot_title,
    )


def create_multi_series_plot(
    runs_data: List[Dict[str, Any]],
    panel_title: str,
    legend_format: str,
    section_dir: Path,
    safe_panel_title: str,
    safe_legend: str,
    output_path: str | None = None,
    plot_title: str | None = None,
) -> None:
    """Create a multi-series plot for different modes (see ``_plot_overlaid_series``)."""
    _plot_overlaid_series(
        runs_data,
        panel_title,
        legend_format,
        section_dir,
        safe_panel_title,
        safe_legend,
        output_path,
        plot_title,
    )


def create_single_series_plots(
    runs_data: List[Dict[str, Any]],
    test_intervals: List[Dict[str, Any]],
    panel_title: str,
    legend_format: str,
    section_dir: Path,
    safe_panel_title: str,
    safe_legend: str,
    window_seconds: int | None = None,
    output_path: str | None = None,
    plot_title: str | None = None,
) -> None:
    """
    Create single-series plots for each interval.

    Args:
        runs_data: List of series data
        test_intervals: List of test interval dictionaries
        panel_title: Panel title
        legend_format: Legend format string
        section_dir: Directory for the section
        safe_panel_title: Sanitized panel title for filename
        safe_legend: Sanitized legend for filename
        window_seconds: Window size for averaging (None for auto-calculation)
        output_path: Optional output path (if None, generates from safe_panel_title and safe_legend)
        plot_title: Optional plot title (if None, generates from panel_title and legend_format)
    """
    if plot_title is None:
        plot_title = f"{panel_title} - {legend_format}"

    # Extract unit from title for y-axis label
    y_axis_label = extract_unit_from_title(plot_title)

    for i, series_data in enumerate(runs_data):
        # Prefer the interval mode recorded on the series by fetch_prometheus_data;
        # runs_data may hold several series per interval, so indexing test_intervals
        # by position is unreliable.
        interval_mode = series_data.get("interval_mode")
        if not interval_mode:
            interval_idx = min(i, len(test_intervals) - 1)
            interval_mode = test_intervals[interval_idx].get(
                "mode", f"interval_{i + 1}"
            )
        mode_suffix = f"_{interval_mode}"

        # Build each filename from the ORIGINAL output_path (kept immutable) so
        # mode suffixes don't compound across series.
        if output_path is None:
            iter_output_path = str(
                section_dir / f"{safe_panel_title}_{safe_legend}{mode_suffix}.png"
            )
        else:
            base = Path(output_path)
            iter_output_path = str(base.parent / f"{base.stem}{mode_suffix}.png")

        create_windowed_plot(
            timestamps=series_data["timestamps"],
            values=series_data["values"],
            title=f"{plot_title} ({interval_mode})",
            output_path=iter_output_path,
            window_seconds=window_seconds,
            y_axis_label=y_axis_label,
        )


def report_failed_fetches(failed_fetches: List[Dict[str, Any]]) -> None:
    """
    Print a summary of failed data fetches.

    Args:
        failed_fetches: List of failure dictionaries
    """
    if not failed_fetches:
        print("\n✅ All data was successfully fetched!")
        return

    print("\n" + "=" * 80)
    print("WARNING: Summary of failed data fetches")
    print("=" * 80)
    print(f"Total failures: {len(failed_fetches)}")
    print("\nPanels/queries that could not be processed:")

    panels_with_errors: Dict[str, List[Dict[str, Any]]] = {}
    for failure in failed_fetches:
        panel_key = failure["panel"]
        if panel_key not in panels_with_errors:
            panels_with_errors[panel_key] = []
        panels_with_errors[panel_key].append(failure)

    for panel, errors in panels_with_errors.items():
        print(f"\nPanel: {panel}")
        for error in errors:
            print(f"  • Query: {error['legend']}")
            print(f"    Interval: {error['interval']}")
            print(f"    Error: {error['error']}")


def build_latency_boxplot(
    test_intervals: List[Dict[str, Any]], output_dir: str
) -> None:
    """Box plot of vendor payment latency per mode from steady-state quantiles.

    Latency is a Prometheus histogram, so there are no individual samples: instead
    each box is built from histogram_quantile values (p5/p25/p50/p75/p95) taken
    over the stabilized (plateau) region of each mode's window.
    """
    from bench_plotter.prometheus_fetch import query_range, matrix_to_per_series_charts
    from .time_series import steady_state_samples, create_precomputed_boxplot

    quantiles = [0.05, 0.25, 0.50, 0.75, 0.95]

    stats: List[Dict[str, Any]] = []
    for interval in test_intervals:
        mode = interval.get("mode", "unknown")
        metric = _LATENCY_BUCKET_METRIC.get(mode)
        if metric is None:
            continue
        ts = interval.get("prometheus_timestamps", {}) or {}
        start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        start_time, end_time = start_ms / 1000, finish_ms / 1000

        qmed: Dict[float, float] = {}
        for q in quantiles:
            expr = (
                f"histogram_quantile({q}, sum(rate("
                f'{metric}{{job="vendor-api", status="success"}}[1m])) by (le))'
            )
            try:
                payload = asyncio.run(
                    query_range(query=expr, start_unix=start_time, end_unix=end_time)
                )
            except Exception as e:
                print(f"Latency box plot: query failed for {mode} q={q}: {e}")
                break
            charts = matrix_to_per_series_charts(
                payload.get("data", {}).get("result", [])
            )
            samples: List[float] = []
            for chart in charts:
                samples = steady_state_samples(chart.get("data", []))
                if samples:
                    break
            if not samples:
                break
            qmed[q] = sorted(samples)[len(samples) // 2]

        if len(qmed) != len(quantiles):
            continue
        stats.append(
            {
                "label": mode,
                "whislo": qmed[0.05],
                "q1": qmed[0.25],
                "med": qmed[0.50],
                "q3": qmed[0.75],
                "whishi": qmed[0.95],
            }
        )

    if not stats:
        print("No latency data for box plot")
        return
    output_path = str(
        Path(output_dir) / "tps_metrics" / "vendor_payment_latency_boxplot.png"
    )
    create_precomputed_boxplot(
        stats,
        "Vendor Payment Latency (steady-state)",
        output_path,
        "Latency (ms)",
    )


# mode -> duration histogram bucket metric (mirrors dashboard_queries/*).
_LATENCY_BUCKET_METRIC = {
    "signature": "payment_request_duration_milliseconds_bucket",
    "payword": "payword_payment_request_duration_milliseconds_bucket",
    "paytree": "paytree_payment_request_duration_milliseconds_bucket",
}


def _le_sort_key(le: str) -> float:
    """Sort ``le`` bucket labels numerically, keeping ``+Inf`` last."""
    return float("inf") if le == "+Inf" else float(le)


def build_latency_distribution(
    test_intervals: List[Dict[str, Any]], output_dir: str
) -> None:
    """ECDF (exact) and violin (reconstructed) of vendor payment latency per mode.

    Latency is a Prometheus histogram, so for each ``le`` bucket we take the
    steady-state (plateau) rate. The cumulative count over the total *is* the
    empirical CDF -- the ECDF is exact, p50/p95/p99 read straight off it. The
    violin's density is reconstructed from the bucket counts (samples spread
    across each bucket), so its shape approximates the distribution rather than
    reproducing measured samples; the figure is titled accordingly.
    """
    from bench_plotter.prometheus_fetch import query_range
    from .time_series import (
        steady_state_samples,
        create_bucket_ecdf,
        create_violin_plot,
    )
    from .histograms import histogram_to_samples

    dists: List[Dict[str, Any]] = []
    for interval in test_intervals:
        mode = interval.get("mode", "unknown")
        metric = _LATENCY_BUCKET_METRIC.get(mode)
        if metric is None:
            continue
        ts = interval.get("prometheus_timestamps", {}) or {}
        start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
        if not start_ms or not finish_ms:
            continue
        start_time, end_time = start_ms / 1000, finish_ms / 1000

        expr = (
            f'sum(rate({metric}{{job="vendor-api", status="success"}}[1m])) by (le)'
        )
        try:
            payload = asyncio.run(
                query_range(query=expr, start_unix=start_time, end_unix=end_time)
            )
        except Exception as e:
            print(f"Latency ECDF: query failed for {mode}: {e}")
            continue

        # Per-le steady-state cumulative rate (buckets are cumulative in ``le``).
        le_value: Dict[str, float] = {}
        for series in payload.get("data", {}).get("result", []):
            le = (series.get("metric") or {}).get("le")
            if le is None:
                continue
            raw = [
                float(p[1])
                for p in series.get("values", [])
                if len(p) >= 2 and p[1] not in (None, "NaN")
            ]
            samples = steady_state_samples(raw)
            if samples:
                le_value[le] = sorted(samples)[len(samples) // 2]
            elif raw:
                le_value[le] = sum(raw) / len(raw)

        if not le_value:
            continue
        total = le_value.get("+Inf")
        if not total or total <= 0:
            total = max(le_value.values())
        if total <= 0:
            continue

        edges: List[float] = []
        cum_fraction: List[float] = []
        for le in sorted(le_value, key=_le_sort_key):
            if le == "+Inf":
                continue
            edges.append(float(le))
            cum_fraction.append(min(1.0, le_value[le] / total))
        if edges:
            dists.append({"label": mode, "edges": edges, "cum_fraction": cum_fraction})

    if not dists:
        print("No latency data for distribution plots")
        return
    tps_dir = Path(output_dir) / "tps_metrics"
    create_bucket_ecdf(
        dists,
        "Vendor Payment Latency (steady-state, ECDF)",
        str(tps_dir / "vendor_payment_latency_ecdf.png"),
        "Latency (ms)",
    )

    # Violin from samples reconstructed off the bucket counts: an approximation
    # of the shape, not measured samples (hence the title), so it must not be
    # re-trimmed -- the tails are the point. trim=False keeps them.
    violin_series = [
        {
            "interval_mode": d["label"],
            "values": histogram_to_samples(d["edges"], d["cum_fraction"]),
        }
        for d in dists
    ]
    create_violin_plot(
        violin_series,
        "Vendor Payment Latency (steady-state, reconstructed from histogram)",
        str(tps_dir / "vendor_payment_latency_violin.png"),
        "Latency (ms)",
        trim=False,
    )


def process_dashboard(
    test_intervals_path: str,
    output_dir: str = "plots",
    num_points: int = 100,
    window_seconds: int | None = None,
    panels_spec: List[Dict[str, Any]] | None = None,
) -> None:
    """
    Process dashboard queries and test intervals to generate plots.

    Args:
        test_intervals_path: Path to test intervals JSON
        output_dir: Directory to save plots
        num_points: Number of interpolation points for time series normalization
        window_seconds: Window size for averaging (None for auto-calculation)
        panels_spec: Optional panel specification (if None, loads from dashboard_queries)

    Uses native Python dashboard format - no JSON parsing needed.
    For single intervals, uses automatic windowed averaging (2x sampling frequency).
    For multiple intervals, uses statistical analysis if same mode, individual plots if different modes.
    """
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)

    # Track failed fetches for final warning
    failed_fetches = []

    # Load test intervals
    test_intervals = load_json_data(test_intervals_path)

    # Drop intervals the benchmark recorded as failed: plotting a failed run's
    # window shows partial/garbage data as if it were a valid measurement.
    # Intervals without a "status" field are kept (backward compatible).
    if isinstance(test_intervals, list):
        kept = [
            iv
            for iv in test_intervals
            if not (isinstance(iv, dict) and iv.get("status") not in (None, "success"))
        ]
        skipped = len(test_intervals) - len(kept)
        if skipped:
            print(f"Skipping {skipped} interval(s) with status != 'success'")
        test_intervals = kept
        if not test_intervals:
            print("No successful intervals to plot")
            return

    # Determine interval type
    is_single_interval, modes = determine_interval_type(test_intervals)

    # Get panels from Python dashboard format if not provided
    panels_spec = get_dashboard_panels(panels_spec)

    if not panels_spec:
        print("No panels found in dashboard configuration")
        return

    # Group TPS panels by title to combine payment modes
    tps_panels_by_title: Dict[str, List[Dict[str, Any]]] = {}
    # Group distribution panels by title to combine payment modes
    distribution_panels_by_title: Dict[str, List[Dict[str, Any]]] = {}
    non_tps_panels = []

    for panel in panels_spec:
        panel_title = panel.get("title", "")
        panel_type = panel.get("type", "timeseries")
        current_section = panel.get("section", "general")

        # Create section directory if this is a row panel
        if panel_type == "row":
            section_dir = Path(output_dir) / current_section
            section_dir.mkdir(exist_ok=True)
            print(f"Created section: {current_section}")
            continue

        # Check if this is a distribution panel (frequency distribution)
        is_distribution = False
        panel_title_lower = panel_title.lower()
        if (
            "frequency distribution" in panel_title_lower
            or "distribution" in panel_title_lower
        ):
            is_distribution = True

        # Check if this is a TPS panel
        is_tps = False
        if not is_distribution:
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                legend_format = target.get("legendFormat", expr)
                if is_tps_panel(panel_title, legend_format, expr):
                    is_tps = True
                    break

        if is_distribution:
            # Group distribution panels by title
            if panel_title not in distribution_panels_by_title:
                distribution_panels_by_title[panel_title] = []
            distribution_panels_by_title[panel_title].append(panel)
        elif is_tps:
            # Group TPS panels by title
            if panel_title not in tps_panels_by_title:
                tps_panels_by_title[panel_title] = []
            tps_panels_by_title[panel_title].append(panel)
        else:
            non_tps_panels.append(panel)

    # Process non-TPS panels normally
    for panel in non_tps_panels:
        panel_title = panel.get("title", "Panel")
        panel_type = panel.get("type", "timeseries")
        current_section = panel.get("section", "general")

        for target in panel.get("targets", []):
            expr = target.get("expr")
            if not expr:
                continue

            legend_format = target.get("legendFormat", expr)

            # Remove __auto from legend_format for cleaner filenames and titles
            if legend_format == "__auto":
                legend_format = panel_title
                # When legend_format was __auto, use only panel_title for filename and title
                use_panel_title_only = True
                # For plot title, use only panel_title (no repetition)
                plot_title = panel_title
            else:
                use_panel_title_only = False
                plot_title = f"{panel_title} - {legend_format}"

            # Fetch data from Prometheus for each test interval
            print(f"Processing panel: {panel_title} - {legend_format}")

            runs_data, interval_failures = fetch_prometheus_data(
                expr, test_intervals, output_dir, panel_title, legend_format
            )
            failed_fetches.extend(interval_failures)

            # Create section directory
            section_dir = Path(output_dir) / current_section
            section_dir.mkdir(exist_ok=True)

            # Sanitize filenames
            safe_panel_title = sanitize_filename(panel_title)
            if use_panel_title_only:
                safe_legend = safe_panel_title
                # When legend_format was __auto, use only panel_title for filename (no duplication)
                filename_suffix = ""
            else:
                safe_legend = sanitize_filename(legend_format)
                filename_suffix = f"_{safe_legend}"

            if runs_data:
                # Detect TPS-like panels and force overlay across modes
                if is_tps_panel(panel_title, legend_format, expr):
                    output_path = str(
                        section_dir / f"{safe_panel_title}{filename_suffix}.png"
                    )
                    create_tps_plot(
                        runs_data,
                        panel_title,
                        legend_format,
                        section_dir,
                        safe_panel_title,
                        safe_legend,
                        output_path,
                        plot_title,
                    )
                    continue

                if is_histogram_query(expr, panel_title, legend_format):
                    print(
                        "Detected histogram query, processing as bar chart (overlaid modes)"
                    )

                    all_histogram_data = process_histogram_data_for_intervals(
                        expr, test_intervals
                    )

                    if all_histogram_data and len(all_histogram_data) == len(
                        test_intervals
                    ):
                        output_path = str(
                            section_dir
                            / f"{safe_panel_title}{filename_suffix}_overlay.png"
                        )
                        create_overlaid_histogram_plot(
                            histogram_data=all_histogram_data,
                            title=plot_title,
                            output_path=str(output_path),
                        )

                elif is_single_interval:
                    if len(test_intervals) > 1:
                        output_path = str(
                            section_dir / f"{safe_panel_title}{filename_suffix}.png"
                        )
                        create_multi_series_plot(
                            runs_data,
                            panel_title,
                            legend_format,
                            section_dir,
                            safe_panel_title,
                            safe_legend,
                            output_path,
                            plot_title,
                        )
                        # Extra steady-state box plot for the vendor/client metrics
                        # that stabilize under sustained load (CPU, network): shows
                        # the distribution of the plateau samples per mode, with the
                        # warm-up ramp and cool-down drain trimmed.
                        if current_section in (
                            "vendor_resources",
                            "client_resources",
                        ) and (
                            panel_title.startswith("Vendor CPU Usage")
                            or panel_title.startswith("Vendor Network")
                            or panel_title.startswith("Client CPU Usage")
                            or panel_title.startswith("Client Network")
                        ):
                            unit_label = extract_unit_from_title(plot_title)
                            stem = f"{safe_panel_title}{filename_suffix}"
                            create_steady_state_boxplot(
                                runs_data,
                                f"{plot_title} (steady-state)",
                                str(section_dir / f"{stem}_boxplot.png"),
                                unit_label,
                            )
                            # Raw plateau samples are available here, so the ECDF
                            # (tail/percentiles) and violin (full density) add
                            # detail the five-number box plot flattens away.
                            create_ecdf_plot(
                                runs_data,
                                f"{plot_title} (steady-state, ECDF)",
                                str(section_dir / f"{stem}_ecdf.png"),
                                unit_label,
                            )
                            create_violin_plot(
                                runs_data,
                                f"{plot_title} (steady-state)",
                                str(section_dir / f"{stem}_violin.png"),
                                unit_label,
                            )
                    else:
                        output_path = str(
                            section_dir / f"{safe_panel_title}{filename_suffix}.png"
                        )
                        create_single_series_plots(
                            runs_data,
                            test_intervals,
                            panel_title,
                            legend_format,
                            section_dir,
                            safe_panel_title,
                            safe_legend,
                            window_seconds,
                            output_path,
                            plot_title,
                        )
                else:
                    output_path = str(
                        section_dir / f"{safe_panel_title}{filename_suffix}.png"
                    )
                    # Extract unit from title for y-axis label
                    y_axis_label = extract_unit_from_title(plot_title)
                    create_mean_std_plot(
                        runs_data=runs_data,
                        title=plot_title,
                        output_path=str(output_path),
                        num_points=num_points,
                        y_axis_label=y_axis_label,
                    )
            else:
                no_data_msg = (
                    f"No data fetched for panel: {panel_title} - {legend_format}"
                )
                print(no_data_msg)
                failed_fetches.append(
                    {
                        "panel": panel_title,
                        "legend": legend_format,
                        "query": expr,
                        "interval": "all intervals",
                        "error": "No data returned",
                    }
                )

    # Process TPS panels grouped by title (combine payment modes)
    for panel_title, panels in tps_panels_by_title.items():
        if len(panels) == 1:
            # Only one panel with this title, process normally
            panel = panels[0]
            current_section = panel.get("section", "general")

            for target in panel.get("targets", []):
                expr = target.get("expr")
                if not expr:
                    continue

                legend_format = target.get("legendFormat", expr)

                # Remove __auto from legend_format for cleaner filenames and titles
                if legend_format == "__auto":
                    legend_format = panel_title
                    use_panel_title_only = True
                    plot_title = panel_title
                else:
                    use_panel_title_only = False
                    plot_title = f"{panel_title} - {legend_format}"

                print(f"Processing panel: {panel_title} - {legend_format}")

                runs_data, interval_failures = fetch_prometheus_data(
                    expr, test_intervals, output_dir, panel_title, legend_format
                )
                failed_fetches.extend(interval_failures)

                section_dir = Path(output_dir) / current_section
                section_dir.mkdir(exist_ok=True)

                safe_panel_title = sanitize_filename(panel_title)
                if use_panel_title_only:
                    safe_legend = safe_panel_title
                    filename_suffix = ""
                else:
                    safe_legend = sanitize_filename(legend_format)
                    filename_suffix = f"_{safe_legend}"

                if runs_data:
                    output_path = str(
                        section_dir / f"{safe_panel_title}{filename_suffix}.png"
                    )
                    y_axis_label = extract_unit_from_title(plot_title)
                    create_tps_plot(
                        runs_data,
                        panel_title,
                        legend_format,
                        section_dir,
                        safe_panel_title,
                        safe_legend,
                        output_path,
                        plot_title,
                    )
        else:
            # Multiple panels with same title - combine payment modes
            print(
                f"Grouping TPS panel '{panel_title}' with {len(panels)} payment modes"
            )

            # Get section from first panel
            current_section = panels[0].get("section", "general")
            section_dir = Path(output_dir) / current_section
            section_dir.mkdir(exist_ok=True)

            # Group targets by quantile (P99, P95, P50) across all panels
            targets_by_quantile: Dict[str, List[Any]] = {}
            has_quantiles = False

            for panel in panels:
                for target in panel.get("targets", []):
                    expr = target.get("expr")
                    if not expr:
                        continue

                    legend_format = target.get("legendFormat", expr)

                    # Remove __auto from legend_format
                    if legend_format == "__auto":
                        legend_format = panel_title

                    # Extract quantile from legend_format (e.g., "Payment P99" -> "P99")
                    quantile = legend_format
                    if "P99" in legend_format or "p99" in legend_format:
                        quantile = "P99"
                        has_quantiles = True
                    elif "P95" in legend_format or "p95" in legend_format:
                        quantile = "P95"
                        has_quantiles = True
                    elif "P50" in legend_format or "p50" in legend_format:
                        quantile = "P50"
                        has_quantiles = True

                    if quantile not in targets_by_quantile:
                        targets_by_quantile[quantile] = []
                    targets_by_quantile[quantile].append((expr, legend_format, panel))

            # If no quantiles found, combine all into a single plot
            if not has_quantiles:
                print("  No quantiles found, creating single combined plot")
                combined_runs_data = []

                for quantile, targets in targets_by_quantile.items():
                    for expr, legend_format, panel in targets:
                        print(f"    Fetching data for: {legend_format}")

                        runs_data, interval_failures = fetch_prometheus_data(
                            expr, test_intervals, output_dir, panel_title, legend_format
                        )
                        failed_fetches.extend(interval_failures)

                        # Derive the payment mode from the expression so series
                        # within the same quantile group are distinguished by mode
                        # (legend formats can collide across payment modes).
                        payment_mode = extract_payment_mode_from_expr(expr)
                        for run_data in runs_data:
                            run_data["payment_mode"] = payment_mode

                        combined_runs_data.extend(runs_data)

                if combined_runs_data:
                    safe_panel_title = sanitize_filename(panel_title)
                    output_path = str(section_dir / f"{safe_panel_title}.png")
                    plot_title = panel_title
                    y_axis_label = extract_unit_from_title(plot_title)

                    # Create combined TPS plot
                    combined_series = []
                    for run_data in combined_runs_data:
                        payment_mode = run_data.get("payment_mode", "unknown")
                        timestamps = run_data.get("timestamps", [])
                        values = run_data.get("values", [])

                        try:
                            ws = (
                                calculate_optimal_window_size(timestamps)
                                if timestamps
                                else None
                            )
                        except Exception:
                            ws = None

                        combined_series.append(
                            {
                                "timestamps": timestamps,
                                "values": values,
                                "label": payment_mode,
                                "window_seconds": ws,
                            }
                        )

                    # Filter out zero values
                    any_nonzero = any(
                        any(
                            (v is not None and float(v) != 0)
                            for v in s.get("values", [])
                        )
                        for s in combined_series
                    )

                    if any_nonzero:
                        series_list = [
                            s
                            for s in combined_series
                            if any(
                                (v is not None and float(v) != 0)
                                for v in s.get("values", [])
                            )
                        ]
                    else:
                        series_list = combined_series

                    create_windowed_plot_multi(
                        series_list=series_list,
                        title=plot_title,
                        output_path=output_path,
                        y_axis_label=y_axis_label,
                    )
            else:
                # For each quantile (P99, P95, P50), create a combined plot with all payment modes
                for quantile, targets in targets_by_quantile.items():
                    print(f"  Creating combined plot for: {panel_title} - {quantile}")

                    combined_runs_data = []

                    for expr, legend_format, panel in targets:
                        print(f"    Fetching data for: {legend_format}")

                        runs_data, interval_failures = fetch_prometheus_data(
                            expr, test_intervals, output_dir, panel_title, legend_format
                        )
                        failed_fetches.extend(interval_failures)

                        # Derive the payment mode from the expression so series
                        # within the same quantile group are distinguished by mode
                        # (legend formats can collide across payment modes).
                        payment_mode = extract_payment_mode_from_expr(expr)
                        for run_data in runs_data:
                            run_data["payment_mode"] = payment_mode

                        combined_runs_data.extend(runs_data)

                    if combined_runs_data:
                        safe_panel_title = sanitize_filename(panel_title)
                        safe_quantile = sanitize_filename(quantile)
                        output_path = str(
                            section_dir / f"{safe_panel_title}_{safe_quantile}.png"
                        )
                        plot_title = f"{panel_title} - {quantile}"
                        y_axis_label = extract_unit_from_title(plot_title)

                        # Create combined TPS plot
                        combined_series = []
                        for run_data in combined_runs_data:
                            payment_mode = run_data.get("payment_mode", "unknown")
                            timestamps = run_data.get("timestamps", [])
                            values = run_data.get("values", [])

                            try:
                                ws = (
                                    calculate_optimal_window_size(timestamps)
                                    if timestamps
                                    else None
                                )
                            except Exception:
                                ws = None

                            combined_series.append(
                                {
                                    "timestamps": timestamps,
                                    "values": values,
                                    "label": payment_mode,
                                    "window_seconds": ws,
                                }
                            )

                        # Filter out zero values
                        any_nonzero = any(
                            any(
                                (v is not None and float(v) != 0)
                                for v in s.get("values", [])
                            )
                            for s in combined_series
                        )

                        if any_nonzero:
                            series_list = [
                                s
                                for s in combined_series
                                if any(
                                    (v is not None and float(v) != 0)
                                    for v in s.get("values", [])
                                )
                            ]
                        else:
                            series_list = combined_series

                        create_windowed_plot_multi(
                            series_list=series_list,
                            title=plot_title,
                            output_path=output_path,
                            y_axis_label=y_axis_label,
                        )

    # Process distribution panels grouped by title (combine payment modes)
    for panel_title, panels in distribution_panels_by_title.items():
        if len(panels) == 1:
            # Only one panel with this title, process normally
            panel = panels[0]
            current_section = panel.get("section", "general")

            for target in panel.get("targets", []):
                expr = target.get("expr")
                if not expr:
                    continue

                legend_format = target.get("legendFormat", expr)

                # Remove __auto from legend_format
                if legend_format == "__auto":
                    legend_format = panel_title

                print(f"Processing distribution panel: {panel_title} - {legend_format}")

                # Process histogram data for all intervals
                all_histogram_data = process_histogram_data_for_intervals(
                    expr, test_intervals
                )

                if all_histogram_data:
                    section_dir = Path(output_dir) / current_section
                    section_dir.mkdir(exist_ok=True)

                    safe_panel_title = sanitize_filename(panel_title)
                    safe_legend = sanitize_filename(legend_format)
                    output_path = str(
                        section_dir / f"{safe_panel_title}_{safe_legend}.png"
                    )
                    plot_title = f"{panel_title} - {legend_format}"

                    create_overlaid_histogram_plot(
                        histogram_data=all_histogram_data,
                        title=plot_title,
                        output_path=output_path,
                    )
        else:
            # Multiple panels with same title - combine payment modes
            print(
                f"Grouping distribution panel '{panel_title}' with {len(panels)} payment modes"
            )

            # Get section from first panel
            current_section = panels[0].get("section", "general")
            section_dir = Path(output_dir) / current_section
            section_dir.mkdir(exist_ok=True)

            # Combine histogram data from all panels
            combined_histogram_data = {}

            for panel in panels:
                for target in panel.get("targets", []):
                    expr = target.get("expr")
                    if not expr:
                        continue

                    # Derive a unique mode label from the metric name in the expression.
                    # Using legendFormat/panel_title is wrong here because all panels share
                    # the same title and __auto legend, causing key collisions that make
                    # all lines show the same (last-written) payment mode's data.
                    mode_label = extract_payment_mode_from_expr(expr)

                    print(
                        f"  Fetching histogram data for: {panel_title} ({mode_label})"
                    )

                    # Only query the interval that matches this payment mode so we don't
                    # run three identical instant-queries per panel.
                    matching_intervals = [
                        i for i in test_intervals if i.get("mode", "") == mode_label
                    ] or test_intervals

                    all_histogram_data = process_histogram_data_for_intervals(
                        expr, matching_intervals
                    )

                    if all_histogram_data:
                        # One line per payment mode — take the first result.
                        _, (buckets, values) = next(iter(all_histogram_data.items()))
                        combined_histogram_data[mode_label] = (buckets, values)

            if combined_histogram_data:
                safe_panel_title = sanitize_filename(panel_title)
                output_path = str(section_dir / f"{safe_panel_title}.png")
                plot_title = panel_title

                create_overlaid_histogram_plot(
                    histogram_data=combined_histogram_data,
                    title=plot_title,
                    output_path=output_path,
                )

    # Steady-state latency distribution: box plot (five quantiles), plus the exact
    # ECDF and a reconstructed violin from the full histogram buckets, which
    # expose the tail the box hides.
    build_latency_boxplot(test_intervals, output_dir)
    build_latency_distribution(test_intervals, output_dir)

    # Final warning summary
    report_failed_fetches(failed_fetches)
