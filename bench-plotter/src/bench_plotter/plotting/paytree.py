"""Paytree payment mode specific plotting functions."""

from .dashboard_processor import process_dashboard


def process_paytree_dashboard(
    test_intervals_path: str,
    output_dir: str = "plots",
    num_points: int = 100,
) -> None:
    """
    Process paytree payment mode dashboard queries and test intervals to generate plots.

    Args:
        test_intervals_path: Path to test intervals JSON
        output_dir: Directory to save plots
        num_points: Number of interpolation points for time series normalization
    """
    # Import here to avoid circular imports
    from bench_plotter.dashboard_queries import get_dashboard_panels

    # Get paytree-specific panels
    panels_spec = get_dashboard_panels(mode="paytree")

    # Process with paytree panels
    process_dashboard(
        test_intervals_path=test_intervals_path,
        output_dir=output_dir,
        num_points=num_points,
        panels_spec=panels_spec,
    )
