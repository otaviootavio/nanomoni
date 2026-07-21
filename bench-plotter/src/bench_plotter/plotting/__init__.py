"""Plotting module organized by payment mode."""

from .common import load_json_data
from .time_series import (
    calculate_sampling_frequency,
    calculate_windowed_averages,
    calculate_optimal_window_size,
    create_windowed_plot,
    create_windowed_plot_multi,
    create_mean_std_plot,
    create_ecdf_plot,
    create_violin_plot,
    create_precomputed_ecdf,
    create_bucket_ecdf,
    normalize_time_series_data,
)
from .histograms import (
    create_histogram_plot,
    create_overlaid_histogram_plot,
    process_histogram_data,
    is_histogram_query,
)
from .dashboard_processor import process_dashboard
from .signature import process_signature_dashboard
from .payword import process_payword_dashboard
from .paytree import process_paytree_dashboard


def process_all_modes(
    test_intervals_path: str,
    output_dir: str = "plots",
    num_points: int = 100,
) -> None:
    """
    Process all payment modes together, generating plots for each.

    Args:
        test_intervals_path: Path to test intervals JSON
        output_dir: Directory to save plots
        num_points: Number of interpolation points for time series normalization
    """
    # Import here to avoid circular imports
    from bench_plotter.dashboard_queries import get_dashboard_panels

    # Get all panels (common + all payment modes)
    panels_spec = get_dashboard_panels(mode="all")

    # Process with all panels
    process_dashboard(
        test_intervals_path=test_intervals_path,
        output_dir=output_dir,
        num_points=num_points,
        panels_spec=panels_spec,
    )


__all__ = [
    "process_dashboard",
    "process_signature_dashboard",
    "process_payword_dashboard",
    "process_paytree_dashboard",
    "process_all_modes",
    "create_windowed_plot",
    "create_windowed_plot_multi",
    "create_histogram_plot",
    "create_mean_std_plot",
    "create_ecdf_plot",
    "create_violin_plot",
    "create_precomputed_ecdf",
    "create_bucket_ecdf",
    "create_overlaid_histogram_plot",
    "normalize_time_series_data",
    "process_histogram_data",
    "is_histogram_query",
    "calculate_sampling_frequency",
    "calculate_windowed_averages",
    "calculate_optimal_window_size",
    "load_json_data",
]
