"""Tests for windowed averaging functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for tests
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from bench_plotter.plotting import (
    calculate_windowed_averages,
    create_windowed_plot,
)


class TestCalculateWindowedAverages:
    """Test windowed averaging calculation."""

    def test_empty_data(self):
        """Test with empty data."""
        timestamps, values = calculate_windowed_averages([], [], 5)
        assert timestamps == []
        assert values == []

    def test_mismatched_lengths(self):
        """Test with mismatched array lengths."""
        timestamps, values = calculate_windowed_averages([1, 2, 3], [1, 2], 5)
        assert timestamps == []
        assert values == []

    def test_single_point(self):
        """Test with single data point."""
        timestamps, values = calculate_windowed_averages([1000.0], [10.0], 5)
        assert timestamps == []
        assert values == []

    def test_basic_windowed_averaging(self):
        """Test basic windowed averaging functionality."""
        timestamps = [1000.0 + i for i in range(10)]  # 1000 to 1009
        values = [i for i in range(10)]  # 0 to 9

        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )

        # Window 1: [1000, 1005)  → values 0-4 → mean 2.0
        # Window 2: [1005, 1009]  → values 5-9 → mean 7.0 (last window includes endpoint)
        assert len(window_centers) == 2
        assert abs(window_averages[0] - 2.0) < 0.001
        assert abs(window_averages[1] - 7.0) < 0.001
        assert window_centers[0] == datetime.fromtimestamp(1002.5, tz=timezone.utc)

    def test_multiple_windows(self):
        """Test with multiple windows."""
        # Create 15 seconds of data
        timestamps = [1000.0 + i for i in range(15)]
        values = [i for i in range(15)]
        
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
            sum([10, 11, 12, 13, 14]) / 5  # 1010-1015
        ]
        
        for actual, expected in zip(window_averages, expected_avgs):
            assert abs(actual - expected) < 0.001

    def test_with_nan_values(self):
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

    def test_unsorted_timestamps(self):
        """Test with unsorted timestamps."""
        timestamps = [1005.0, 1000.0, 1003.0, 1001.0, 1004.0]
        values = [5, 0, 3, 1, 4]  # Corresponding values
        
        window_centers, window_averages = calculate_windowed_averages(
            timestamps, values, window_seconds=5
        )
        
        # Should sort and calculate correctly
        assert len(window_centers) == 1
        expected_avg = sum([0, 1, 3, 4, 5]) / 5  # All values in window
        assert abs(window_averages[0] - expected_avg) < 0.001


class TestCreateWindowedPlot:
    """Test windowed plot creation."""

    def test_empty_data(self):
        """Test with empty data — no file should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "should_not_exist.png")
            create_windowed_plot([], [], output_path=output_path)
            assert not Path(output_path).exists()

    def test_basic_plot_creation(self):
        """Test basic plot creation."""
        # Create test data
        timestamps = [1000.0 + i for i in range(10)]
        values = [i for i in range(10)]
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name
        
        try:
            create_windowed_plot(
                timestamps, values,
                title="Test Plot",
                output_path=temp_path,
                window_seconds=3
            )
            
            # Verify file was created
            assert Path(temp_path).exists()
            
        finally:
            if Path(temp_path).exists():
                Path(temp_path).unlink()

    def test_large_window_size(self):
        """Test with a window larger than the data range — all points fall in one window."""
        timestamps = [1000.0, 1001.0, 1002.0]
        values = [1, 2, 3]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "plot.png")
            create_windowed_plot(timestamps, values, output_path=output_path, window_seconds=10)
            # One window covers all data → plot is created
            assert Path(output_path).exists()


# TestProcessGrafanaDashboardWindowed removed — process_grafana_dashboard no longer exists.
class _Removed:
    """Test integration of windowed plotting in dashboard processing."""

    def test_single_interval_detection(self):
        """Test that single intervals use windowed plotting."""
        # Mock data for single interval
        single_interval = [{
            "status": "success",
            "prometheus_timestamps": {
                "start_ms": 1000000,
                "finish_ms": 1005000
            }
        }]
        
        dashboard = {
            "panels": [{
                "id": 1,
                "title": "Test Panel",
                "targets": [{"expr": "up", "legendFormat": "test"}]
            }]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "dashboard.json"
            intervals_path = Path(temp_dir) / "intervals.json"
            output_dir = Path(temp_dir) / "plots"
            
            # Write test files
            import json
            dashboard_path.write_text(json.dumps(dashboard))
            intervals_path.write_text(json.dumps(single_interval))
            
            # Mock the Prometheus fetch and plotting functions
            with patch('bench_plotter.prometheus_fetch.matrix_to_per_series_charts') as mock_charts, \
                 patch('bench_plotter.plotting.create_windowed_plot') as mock_windowed, \
                 patch('bench_plotter.prometheus_fetch.query_range') as mock_query:
                
                # Mock Prometheus response
                mock_query.return_value = {
                    'data': {
                        'result': [{
                            'metric': {'__name__': 'up'},
                            'values': [[1000, '1'], [1005, '2'], [1010, '1']]
                        }]
                    }
                }
                
                # Mock chart conversion
                mock_charts.return_value = [{
                    'timestamps': [1000.0, 1005.0, 1010.0],
                    'values': [1.0, 2.0, 1.0]
                }]
                
                # Process dashboard
                process_grafana_dashboard(
                    str(dashboard_path),
                    str(intervals_path),
                    str(output_dir),
                    window_seconds=5
                )
                
                # Verify windowed plotting was called
                mock_windowed.assert_called_once()
                call_args = mock_windowed.call_args
                assert call_args[1]['window_seconds'] == 5
                assert 'Window' in call_args[1]['title']

    def test_multiple_intervals_use_statistical(self):
        """Test that multiple intervals use statistical plotting."""
        # Mock data for multiple intervals
        multiple_intervals = [
            {
                "status": "success",
                "prometheus_timestamps": {
                    "start_ms": 1000000,
                    "finish_ms": 1005000
                }
            },
            {
                "status": "success", 
                "prometheus_timestamps": {
                    "start_ms": 2000000,
                    "finish_ms": 2005000
                }
            }
        ]
        
        dashboard = {
            "panels": [{
                "id": 1,
                "title": "Test Panel",
                "targets": [{"expr": "up", "legendFormat": "test"}]
            }]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "dashboard.json"
            intervals_path = Path(temp_dir) / "intervals.json"
            output_dir = Path(temp_dir) / "plots"
            
            # Write test files
            import json
            dashboard_path.write_text(json.dumps(dashboard))
            intervals_path.write_text(json.dumps(multiple_intervals))
            
            # Mock the Prometheus fetch and plotting functions
            with patch('bench_plotter.prometheus_fetch.matrix_to_per_series_charts') as mock_charts, \
                 patch('bench_plotter.plotting.create_mean_std_plot') as mock_statistical, \
                 patch('bench_plotter.prometheus_fetch.query_range') as mock_query:
                
                # Mock Prometheus response
                mock_query.return_value = {
                    'data': {
                        'result': [{
                            'metric': {'__name__': 'up'},
                            'values': [[1000, '1'], [1005, '2'], [1010, '1']]
                        }]
                    }
                }
                
                # Mock chart conversion
                mock_charts.return_value = [{
                    'timestamps': [1000.0, 1005.0, 1010.0],
                    'values': [1.0, 2.0, 1.0]
                }]
                
                # Process dashboard
                process_grafana_dashboard(
                    str(dashboard_path),
                    str(intervals_path),
                    str(output_dir),
                    window_seconds=5
                )
                
                # Verify statistical plotting was called (not windowed)
                mock_statistical.assert_called_once()
                # windowed plot should not be called for multiple intervals
                assert mock_statistical.call_count == 1

    def test_multiple_modes_legend_only_shows_modes(self):
        """Test that multiple-mode legends show only mode names."""
        multiple_intervals = [
            {
                "status": "success",
                "mode": "signature",
                "prometheus_timestamps": {
                    "start_ms": 1000000,
                    "finish_ms": 1005000
                }
            },
            {
                "status": "success",
                "mode": "paytree",
                "prometheus_timestamps": {
                    "start_ms": 2000000,
                    "finish_ms": 2005000
                }
            }
        ]

        dashboard = {
            "panels": [{
                "id": 1,
                "title": "Test Panel",
                "targets": [{"expr": "up", "legendFormat": "Uptime"}]
            }]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "dashboard.json"
            intervals_path = Path(temp_dir) / "intervals.json"
            output_dir = Path(temp_dir) / "plots"

            import json
            dashboard_path.write_text(json.dumps(dashboard))
            intervals_path.write_text(json.dumps(multiple_intervals))

            with patch('bench_plotter.prometheus_fetch.matrix_to_per_series_charts') as mock_charts, \
                 patch('bench_plotter.plotting.create_windowed_plot_multi') as mock_multi, \
                 patch('bench_plotter.prometheus_fetch.query_range', new_callable=AsyncMock) as mock_query_range:
                mock_query_range.return_value = {
                    'data': {
                        'result': [{
                            'metric': {'__name__': 'up'},
                            'values': [[1000, '1'], [1005, '2'], [1010, '1']]
                        }]
                    }
                }
                mock_charts.return_value = [
                    {
                        'timestamps': [1000.0, 1005.0, 1010.0],
                        'data': [1.0, 2.0, 1.0]
                    }
                ]
                process_grafana_dashboard(
                    str(dashboard_path),
                    str(intervals_path),
                    str(output_dir),
                    window_seconds=5
                )

                assert mock_multi.called
                # Ensure labels are only the mode names and not the full query text
                series_list = mock_multi.call_args[1]['series_list']
                assert [series['label'] for series in series_list] == ['signature', 'paytree']
