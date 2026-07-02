"""Tests for plotting module - the core functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for tests
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from bench_plotter.plotting import (
    create_mean_std_plot,
    load_json_data,
    normalize_time_series_data,
)


class TestLoadJsonData:
    """Test JSON data loading functionality."""

    def test_load_valid_json(self):
        """Test loading valid JSON file."""
        test_data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = load_json_data(temp_path)
            assert result == test_data
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_json_data("/nonexistent/path.json")

    def test_load_invalid_json(self):
        """Test loading invalid JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_json_data(temp_path)
        finally:
            os.unlink(temp_path)


class TestNormalizeTimeSeriesData:
    """Test time series normalization functionality."""

    def test_empty_data(self):
        """Test normalization with empty data."""
        result = normalize_time_series_data([], 100)
        assert result.empty

    def test_single_run_normalization(self):
        """Test normalization of single time series run."""
        runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [1.0, 2.0, 3.0]
            }
        ]
        result = normalize_time_series_data(runs_data, 50)
        
        assert len(result) == 50
        assert 'relative_time' in result.columns
        assert 'value' in result.columns
        assert all(0 <= t <= 1 for t in result['relative_time'])

    def test_multiple_runs_normalization(self):
        """Test normalization of multiple time series runs."""
        runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [1.0, 2.0, 3.0]
            },
            {
                "timestamps": [1000, 1005, 1010, 1015, 1020],
                "values": [1.5, 2.5, 3.5, 4.5, 5.5]
            }
        ]
        result = normalize_time_series_data(runs_data, 100)
        
        assert len(result) == 200  # 100 points * 2 runs
        assert 'run_id' in result.columns
        assert result['run_id'].nunique() == 2

    def test_invalid_timestamps(self):
        """Test handling of invalid timestamps."""
        runs_data = [
            {
                "timestamps": [],
                "values": [1.0, 2.0]
            },
            {
                "timestamps": [1000, 1010],
                "values": []
            }
        ]
        result = normalize_time_series_data(runs_data, 50)
        assert result.empty

    def test_zero_duration(self):
        """Test handling of zero duration timestamps."""
        runs_data = [
            {
                "timestamps": [1000, 1000, 1000],  # Same timestamp
                "values": [1.0, 2.0, 3.0]
            }
        ]
        result = normalize_time_series_data(runs_data, 50)
        assert result.empty

    def test_nan_values_handling(self):
        """Test handling of NaN values in data."""
        runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [1.0, np.nan, 3.0]
            }
        ]
        result = normalize_time_series_data(runs_data, 50)
        
        # Should drop NaN values and continue
        assert len(result) == 50
        assert not result['value'].isna().all()


class TestCreateMeanStdPlot:
    """Test plot creation functionality."""

    def setup_method(self):
        """Set up test data for plotting tests."""
        self.test_runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [1.0, 2.0, 3.0]
            },
            {
                "timestamps": [1000, 1005, 1010, 1015, 1020],
                "values": [1.5, 2.5, 3.5, 4.5, 5.5]
            }
        ]

    def test_create_plot_valid_data(self):
        """Test creating plot with valid data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "test_plot.png")
            
            create_mean_std_plot(
                runs_data=self.test_runs_data,
                title="Test Plot",
                output_path=output_path,
                num_points=50
            )
            
            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0

    def test_create_plot_empty_data(self):
        """Test creating plot with empty data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "empty_plot.png")
            
            create_mean_std_plot(
                runs_data=[],
                title="Empty Plot",
                output_path=output_path
            )
            
            # Should not create file for empty data
            assert not os.path.exists(output_path)

    def test_create_plot_no_valid_data(self):
        """Test creating plot with no valid data after normalization."""
        runs_data = [
            {
                "timestamps": [],
                "values": []
            }
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "invalid_plot.png")
            
            create_mean_std_plot(
                runs_data=runs_data,
                title="Invalid Plot",
                output_path=output_path
            )
            
            assert not os.path.exists(output_path)

    def test_create_plot_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = os.path.join(temp_dir, "nested", "directory")
            output_path = os.path.join(nested_dir, "test_plot.png")
            
            create_mean_std_plot(
                runs_data=self.test_runs_data,
                title="Test Plot",
                output_path=output_path
            )
            
            assert os.path.exists(output_path)
            assert os.path.isdir(nested_dir)

    def test_single_value_handling(self):
        """Test plot creation with single value (std = 0)."""
        runs_data = [
            {
                "timestamps": [1000, 1010, 1020],
                "values": [5.0, 5.0, 5.0]  # All same values
            }
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "single_value_plot.png")
            
            create_mean_std_plot(
                runs_data=runs_data,
                title="Single Value Plot",
                output_path=output_path
            )

            assert os.path.exists(output_path)


# TestProcessGrafanaDashboard removed — process_grafana_dashboard was replaced by process_dashboard.
# Integration coverage lives in test_integration.py.
class _Removed:
    """Test the main dashboard processing functionality."""

    def setup_method(self):
        """Set up test dashboard and intervals."""
        self.test_dashboard = {
            "panels": [
                {
                    "id": 1,
                    "title": "Test Panel",
                    "type": "graph",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": "up", "legendFormat": "Uptime"}
                    ]
                }
            ]
        }
        
        self.test_intervals = [
            {
                "status": "success",
                "prometheus_timestamps": {
                    "start_ms": 1000000,
                    "finish_ms": 1000100
                }
            }
        ]

    @patch('bench_plotter.plotting.asyncio.run')
    @patch('bench_plotter.plotting.query_range')
    @patch('bench_plotter.plotting.matrix_to_per_series_charts')
    def test_successful_processing(self, mock_charts, mock_query, mock_asyncio):
        """Test successful dashboard processing."""
        # Mock successful data fetch
        mock_query.return_value = {
            "data": {"result": []}
        }
        mock_charts.return_value = [
            {
                "timestamps": [1000, 1010],
                "data": [1.0, 2.0]
            }
        ]
        mock_asyncio.return_value = mock_query.return_value
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary files
            dashboard_path = os.path.join(temp_dir, "dashboard.json")
            intervals_path = os.path.join(temp_dir, "intervals.json")
            output_dir = os.path.join(temp_dir, "output")
            
            with open(dashboard_path, 'w') as f:
                json.dump(self.test_dashboard, f)
            with open(intervals_path, 'w') as f:
                json.dump(self.test_intervals, f)
            
            process_grafana_dashboard(
                dashboard_path=dashboard_path,
                test_intervals_path=intervals_path,
                output_dir=output_dir,
                num_points=50
            )
            
            assert os.path.exists(output_dir)

    def test_invalid_dashboard(self):
        """Test processing with invalid dashboard."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = os.path.join(temp_dir, "invalid.json")
            intervals_path = os.path.join(temp_dir, "intervals.json")
            
            with open(dashboard_path, 'w') as f:
                json.dump({"invalid": "structure"}, f)
            with open(intervals_path, 'w') as f:
                json.dump(self.test_intervals, f)
            
            # Should not raise exception but handle gracefully
            process_grafana_dashboard(
                dashboard_path=dashboard_path,
                test_intervals_path=intervals_path,
                output_dir=temp_dir
            )

    def test_nonexistent_files(self):
        """Test processing with non-existent files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Should handle non-existent files gracefully
            process_grafana_dashboard(
                dashboard_path="/nonexistent/dashboard.json",
                test_intervals_path="/nonexistent/intervals.json",
                output_dir=temp_dir
            )

    @patch('bench_plotter.plotting.asyncio.run')
    def test_fetch_error_handling(self, mock_asyncio):
        """Test handling of fetch errors during processing."""
        # Mock fetch error
        mock_asyncio.side_effect = Exception("Network error")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = os.path.join(temp_dir, "dashboard.json")
            intervals_path = os.path.join(temp_dir, "intervals.json")
            
            with open(dashboard_path, 'w') as f:
                json.dump(self.test_dashboard, f)
            with open(intervals_path, 'w') as f:
                json.dump(self.test_intervals, f)
            
            # Should handle errors gracefully and show warning
            process_grafana_dashboard(
                dashboard_path=dashboard_path,
                test_intervals_path=intervals_path,
                output_dir=temp_dir
            )

    def test_row_panel_handling(self):
        """Test handling of row panels in dashboard."""
        dashboard_with_rows = {
            "panels": [
                {
                    "id": 1,
                    "title": "Row Section",
                    "type": "row"
                },
                {
                    "id": 2,
                    "title": "Panel in Row",
                    "type": "graph",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": "up", "legendFormat": "Uptime"}
                    ]
                }
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = os.path.join(temp_dir, "dashboard.json")
            intervals_path = os.path.join(temp_dir, "intervals.json")
            output_dir = os.path.join(temp_dir, "output")
            
            with open(dashboard_path, 'w') as f:
                json.dump(dashboard_with_rows, f)
            with open(intervals_path, 'w') as f:
                json.dump(self.test_intervals, f)
            
            # Mock the async parts to avoid network calls
            with patch('bench_plotter.plotting.asyncio.run') as mock_asyncio, \
                 patch('bench_plotter.plotting.matrix_to_per_series_charts') as mock_charts:
                
                mock_asyncio.return_value = {"data": {"result": []}}
                mock_charts.return_value = []
                
                process_grafana_dashboard(
                    dashboard_path=dashboard_path,
                    test_intervals_path=intervals_path,
                    output_dir=output_dir
                )
                
                # Should create section directory
                section_dir = os.path.join(output_dir, "row_section")
                assert os.path.exists(section_dir)

    def test_filename_sanitization(self):
        """Test that panel titles are properly sanitized for filenames."""
        dashboard_with_special_chars = {
            "panels": [
                {
                    "id": 1,
                    "title": "Test Panel (Special) / Chars: *?\"<>|",
                    "type": "graph",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": "up", "legendFormat": "Legend (Special)"}
                    ]
                }
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = os.path.join(temp_dir, "dashboard.json")
            intervals_path = os.path.join(temp_dir, "intervals.json")
            output_dir = os.path.join(temp_dir, "output")
            
            with open(dashboard_path, 'w') as f:
                json.dump(dashboard_with_special_chars, f)
            with open(intervals_path, 'w') as f:
                json.dump(self.test_intervals, f)
            
            # Mock the async parts
            with patch('bench_plotter.plotting.asyncio.run') as mock_asyncio, \
                 patch('bench_plotter.plotting.matrix_to_per_series_charts') as mock_charts:
                
                mock_asyncio.return_value = {"data": {"result": []}}
                mock_charts.return_value = [
                    {
                        "timestamps": [1000, 1010],
                        "data": [1.0, 2.0]
                    }
                ]
                
                process_grafana_dashboard(
                    dashboard_path=dashboard_path,
                    test_intervals_path=intervals_path,
                    output_dir=output_dir
                )
                
                # Should create files with sanitized names
                files = list(Path(output_dir).glob("*.png"))
                assert len(files) > 0
                # Check that filenames don't contain special characters
                for file in files:
                    assert not any(char in file.name for char in '()/:*?"<>|')

    def test_warning_summary_with_failures(self):
        """Test that warning summary is displayed when there are failures."""
        with patch('bench_plotter.plotting.asyncio.run') as mock_asyncio, \
             patch('bench_plotter.plotting.matrix_to_per_series_charts') as mock_charts, \
             patch('builtins.print') as mock_print:
            
            # Mock fetch failure
            mock_asyncio.side_effect = Exception("Fetch error")
            mock_charts.return_value = []
            
            with tempfile.TemporaryDirectory() as temp_dir:
                dashboard_path = os.path.join(temp_dir, "dashboard.json")
                intervals_path = os.path.join(temp_dir, "intervals.json")
                
                with open(dashboard_path, 'w') as f:
                    json.dump(self.test_dashboard, f)
                with open(intervals_path, 'w') as f:
                    json.dump(self.test_intervals, f)
                
                process_grafana_dashboard(
                    dashboard_path=dashboard_path,
                    test_intervals_path=intervals_path,
                    output_dir=temp_dir
                )
                
                # Check that warning was printed
                print_calls = [str(call) for call in mock_print.call_args_list]
                warning_found = any("AVISO FINAL" in call for call in print_calls)
                assert warning_found
