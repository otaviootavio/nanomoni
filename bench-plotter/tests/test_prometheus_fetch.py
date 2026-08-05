"""Tests for prometheus_fetch module."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from bench_plotter.prometheus_fetch import (
    _step_for_range_seconds,
    query_range,
)
from bench_plotter.prometheus_matrix import (
    matrix_to_per_series_charts,
)


class TestStepForRangeSeconds:
    def test_small_window(self) -> None:
        # Step is the 5s floor (covers the 10s vendor-api rate() window with
        # no gap) for any window under Prometheus's per-series point cap.
        assert _step_for_range_seconds(300) == "5s"

    def test_medium_window(self) -> None:
        assert _step_for_range_seconds(3600) == "5s"

    def test_large_window(self) -> None:
        # 12h stays under the new (5s-floor) point cap of ~15.3h.
        assert _step_for_range_seconds(12 * 3600) == "5s"

    def test_window_at_point_cap_stays_5s(self) -> None:
        # 11_000 points * 5s == 55_000s: right at the cap, still 5s.
        assert _step_for_range_seconds(11_000 * 5) == "5s"

    def test_window_over_point_cap_widens_step(self) -> None:
        # Beyond the cap the step widens just enough to stay under it, rather
        # than letting Prometheus reject the query with too many points.
        assert _step_for_range_seconds(16 * 3600) == "6s"


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
