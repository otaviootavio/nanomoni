"""Tests for windowed averaging functionality."""

import os
import tempfile
from pathlib import Path
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend for tests
import numpy as np
from datetime import datetime, timezone

from bench_plotter.plotting import (
    calculate_windowed_averages,
    create_windowed_plot,
)


class TestCalculateWindowedAverages:
    """Test windowed averaging calculation."""

    def test_empty_data(self) -> None:
        """Test with empty data."""
        timestamps, values = calculate_windowed_averages([], [], 5)
        assert timestamps == []
        assert values == []

    def test_mismatched_lengths(self) -> None:
        """Test with mismatched array lengths."""
        timestamps, values = calculate_windowed_averages([1, 2, 3], [1, 2], 5)
        assert timestamps == []
        assert values == []

    def test_single_point(self) -> None:
        """Test with single data point."""
        timestamps, values = calculate_windowed_averages([1000.0], [10.0], 5)
        assert timestamps == []
        assert values == []

    def test_basic_windowed_averaging(self) -> None:
        """Test basic windowed averaging functionality."""
        timestamps = [1000.0 + i for i in range(10)]  # 1000 to 1009
        values = [float(i) for i in range(10)]  # 0 to 9

        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )

        # Window 1: [1000, 1005)  → values 0-4 → mean 2.0
        # Window 2: [1005, 1009]  → values 5-9 → mean 7.0 (last window includes endpoint)
        assert len(window_centers) == 2
        assert abs(window_averages[0] - 2.0) < 0.001
        assert abs(window_averages[1] - 7.0) < 0.001
        assert window_centers[0] == datetime.fromtimestamp(1002.5, tz=timezone.utc)

    def test_multiple_windows(self) -> None:
        """Test with multiple windows."""
        # Create 15 seconds of data
        timestamps = [1000.0 + i for i in range(15)]
        values = [float(i) for i in range(15)]

        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )

        # Should have windows: 1000-1005, 1005-1010, 1010-1015
        assert len(window_centers) == 3
        assert len(window_averages) == 3

        # Check values for each window
        expected_avgs = [
            sum([0, 1, 2, 3, 4]) / 5,  # 1000-1005
            sum([5, 6, 7, 8, 9]) / 5,  # 1005-1010
            sum([10, 11, 12, 13, 14]) / 5,  # 1010-1015
        ]

        for actual, expected in zip(window_averages, expected_avgs):
            assert abs(actual - expected) < 0.001

    def test_with_nan_values(self) -> None:
        """Test handling of NaN values."""
        timestamps = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]
        values = [1.0, np.nan, 3.0, 4.0, 5.0]  # One NaN value

        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )

        # Should filter out NaN and average remaining values
        assert len(window_centers) == 1
        expected_avg = sum([1.0, 3.0, 4.0, 5.0]) / 4  # Excluding NaN
        assert abs(window_averages[0] - expected_avg) < 0.001

    def test_unsorted_timestamps(self) -> None:
        """Test with unsorted timestamps."""
        timestamps = [1005.0, 1000.0, 1003.0, 1001.0, 1004.0]
        values = [5.0, 0.0, 3.0, 1.0, 4.0]  # Corresponding values

        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )

        # Should sort and calculate correctly
        assert len(window_centers) == 1
        expected_avg = sum([0, 1, 3, 4, 5]) / 5  # All values in window
        assert abs(window_averages[0] - expected_avg) < 0.001


class TestCreateWindowedPlot:
    """Test windowed plot creation."""

    def test_empty_data(self) -> None:
        """Test with empty data — no file should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "should_not_exist.png")
            create_windowed_plot([], [], output_path=output_path)
            assert not Path(output_path).exists()

    def test_basic_plot_creation(self) -> None:
        """Test basic plot creation."""
        # Create test data
        timestamps = [1000.0 + i for i in range(10)]
        values = [float(i) for i in range(10)]

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name

        try:
            create_windowed_plot(
                timestamps,
                values,
                title="Test Plot",
                output_path=temp_path,
                window_seconds=3,
            )

            # Verify file was created
            assert Path(temp_path).exists()

        finally:
            if Path(temp_path).exists():
                Path(temp_path).unlink()

    def test_large_window_size(self) -> None:
        """Test with a window larger than the data range — all points fall in one window."""
        timestamps = [1000.0, 1001.0, 1002.0]
        values = [1.0, 2.0, 3.0]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "plot.png")
            create_windowed_plot(
                timestamps, values, output_path=output_path, window_seconds=10
            )
            # One window covers all data → plot is created
            assert Path(output_path).exists()
