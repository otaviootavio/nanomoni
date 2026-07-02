"""Tests for plotting module - the core functionality."""

import json
import os
import tempfile
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend for tests
import numpy as np
import pytest

from bench_plotter.plotting import (
    create_mean_std_plot,
    load_json_data,
    normalize_time_series_data,
)


class TestLoadJsonData:
    """Test JSON data loading functionality."""

    def test_load_valid_json(self) -> None:
        """Test loading valid JSON file."""
        test_data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = load_json_data(temp_path)
            assert result == test_data
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self) -> None:
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_json_data("/nonexistent/path.json")

    def test_load_invalid_json(self) -> None:
        """Test loading invalid JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_json_data(temp_path)
        finally:
            os.unlink(temp_path)


class TestNormalizeTimeSeriesData:
    """Test time series normalization functionality."""

    def test_empty_data(self) -> None:
        """Test normalization with empty data."""
        result = normalize_time_series_data([], 100)
        assert result.empty

    def test_single_run_normalization(self) -> None:
        """Test normalization of single time series run."""
        runs_data = [{"timestamps": [1000, 1010, 1020], "values": [1.0, 2.0, 3.0]}]
        result = normalize_time_series_data(runs_data, 50)

        assert len(result) == 50
        assert "relative_time" in result.columns
        assert "value" in result.columns
        assert all(0 <= t <= 1 for t in result["relative_time"])

    def test_multiple_runs_normalization(self) -> None:
        """Test normalization of multiple time series runs."""
        runs_data = [
            {"timestamps": [1000, 1010, 1020], "values": [1.0, 2.0, 3.0]},
            {
                "timestamps": [1000, 1005, 1010, 1015, 1020],
                "values": [1.5, 2.5, 3.5, 4.5, 5.5],
            },
        ]
        result = normalize_time_series_data(runs_data, 100)

        assert len(result) == 200  # 100 points * 2 runs
        assert "run_id" in result.columns
        assert result["run_id"].nunique() == 2

    def test_invalid_timestamps(self) -> None:
        """Test handling of invalid timestamps."""
        runs_data: list[dict[str, Any]] = [
            {"timestamps": [], "values": [1.0, 2.0]},
            {"timestamps": [1000, 1010], "values": []},
        ]
        result = normalize_time_series_data(runs_data, 50)
        assert result.empty

    def test_zero_duration(self) -> None:
        """Test handling of zero duration timestamps."""
        runs_data = [
            {
                "timestamps": [1000, 1000, 1000],  # Same timestamp
                "values": [1.0, 2.0, 3.0],
            }
        ]
        result = normalize_time_series_data(runs_data, 50)
        assert result.empty

    def test_nan_values_handling(self) -> None:
        """Test handling of NaN values in data."""
        runs_data = [{"timestamps": [1000, 1010, 1020], "values": [1.0, np.nan, 3.0]}]
        result = normalize_time_series_data(runs_data, 50)

        # Should drop NaN values and continue
        assert len(result) == 50
        assert not result["value"].isna().all()


class TestCreateMeanStdPlot:
    """Test plot creation functionality."""

    def setup_method(self) -> None:
        """Set up test data for plotting tests."""
        self.test_runs_data = [
            {"timestamps": [1000, 1010, 1020], "values": [1.0, 2.0, 3.0]},
            {
                "timestamps": [1000, 1005, 1010, 1015, 1020],
                "values": [1.5, 2.5, 3.5, 4.5, 5.5],
            },
        ]

    def test_create_plot_valid_data(self) -> None:
        """Test creating plot with valid data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "test_plot.png")

            create_mean_std_plot(
                runs_data=self.test_runs_data,
                title="Test Plot",
                output_path=output_path,
                num_points=50,
            )

            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0

    def test_create_plot_empty_data(self) -> None:
        """Test creating plot with empty data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "empty_plot.png")

            create_mean_std_plot(
                runs_data=[], title="Empty Plot", output_path=output_path
            )

            # Should not create file for empty data
            assert not os.path.exists(output_path)

    def test_create_plot_no_valid_data(self) -> None:
        """Test creating plot with no valid data after normalization."""
        runs_data: list[dict[str, Any]] = [{"timestamps": [], "values": []}]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "invalid_plot.png")

            create_mean_std_plot(
                runs_data=runs_data, title="Invalid Plot", output_path=output_path
            )

            assert not os.path.exists(output_path)

    def test_create_plot_directory_creation(self) -> None:
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = os.path.join(temp_dir, "nested", "directory")
            output_path = os.path.join(nested_dir, "test_plot.png")

            create_mean_std_plot(
                runs_data=self.test_runs_data,
                title="Test Plot",
                output_path=output_path,
            )

            assert os.path.exists(output_path)
            assert os.path.isdir(nested_dir)

    def test_single_value_handling(self) -> None:
        """Test plot creation with single value (std = 0)."""
        runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [5.0, 5.0, 5.0],  # All same values
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "single_value_plot.png")

            create_mean_std_plot(
                runs_data=runs_data, title="Single Value Plot", output_path=output_path
            )

            assert os.path.exists(output_path)
