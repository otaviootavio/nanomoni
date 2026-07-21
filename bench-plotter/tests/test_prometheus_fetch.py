"""Tests for prometheus_fetch module."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from bench_plotter.prometheus_fetch import (
    range_step_for_window,
    query_range,
)
from bench_plotter.prometheus_matrix import (
    matrix_to_per_series_charts,
)


class TestRangeStepForWindow:
    def test_small_window(self) -> None:
        # Step is the 15s scrape_interval for any window under Prometheus's
        # per-series point cap.
        assert range_step_for_window(300) == "15s"

    def test_medium_window(self) -> None:
        assert range_step_for_window(3600) == "15s"

    def test_large_window(self) -> None:
        assert range_step_for_window(24 * 3600) == "15s"

    def test_window_at_point_cap_stays_15s(self) -> None:
        # 11_000 points * 15s == 165_000s: right at the cap, still 15s.
        assert range_step_for_window(11_000 * 15) == "15s"

    def test_window_over_point_cap_widens_step(self) -> None:
        # Beyond the cap the step widens just enough to stay under it, rather
        # than letting Prometheus reject the query with too many points.
        assert range_step_for_window(48 * 3600) == "16s"


class TestQueryRange:
    @patch("bench_plotter.prometheus_fetch.httpx.AsyncClient")
    def test_successful_query(self, mock_client: MagicMock) -> None:
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"status": "success", "data": {"result": []}}
        )
        mock_response.raise_for_status = Mock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        result = asyncio.run(
            query_range(query="up", start_unix=1000.0, end_unix=2000.0, step="15s")
        )
        assert result == {"status": "success", "data": {"result": []}}

    @patch("bench_plotter.prometheus_fetch.httpx.AsyncClient")
    def test_query_failure(self, mock_client: MagicMock) -> None:
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"status": "error", "error": "bad query"}
        )
        mock_response.raise_for_status = Mock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ValueError, match="Prometheus query failed: bad query"):
            asyncio.run(
                query_range(query="invalid", start_unix=1000.0, end_unix=2000.0)
            )


class TestMatrixToPerSeriesCharts:
    def test_empty_matrix(self) -> None:
        result = matrix_to_per_series_charts([])
        assert result == []

    def test_single_series_with_name(self) -> None:
        matrix = [
            {
                "metric": {"__name__": "up", "job": "test"},
                "values": [[1000, "1.0"], [1015, "2.0"]],
            }
        ]
        result = matrix_to_per_series_charts(matrix)
        assert len(result) == 1
        assert result[0]["metric_name"] == "up"
        assert result[0]["title"] == "up"
        assert result[0]["subtitle"] == 'job="test"'
        assert result[0]["data"] == [1.0, 2.0]
        assert result[0]["labels"] == ["00:16:40", "00:16:55"]

    def test_single_series_without_name(self) -> None:
        matrix = [{"metric": {"job": "test"}, "values": [[1000, "1.0"], [1015, "2.0"]]}]
        result = matrix_to_per_series_charts(matrix)
        assert result[0]["metric_name"] == "series"
        assert result[0]["subtitle"] == 'job="test"'
