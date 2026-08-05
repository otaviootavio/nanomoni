"""Tests for pyroscope_fetch module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from bench_plotter.pyroscope_fetch import render


class TestRender:
    @patch("bench_plotter.pyroscope_fetch.httpx.AsyncClient")
    def test_successful_query(self, mock_client: MagicMock) -> None:
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"flamebearer": {"names": [], "levels": []}}
        )
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        result = asyncio.run(
            render(
                query="process_cpu:cpu:nanoseconds:cpu:nanoseconds{}",
                start_unix=1000.0,
                end_unix=2000.0,
            )
        )
        assert result == {"flamebearer": {"names": [], "levels": []}}

    @patch("bench_plotter.pyroscope_fetch.httpx.AsyncClient")
    def test_query_failure_raises(self, mock_client: MagicMock) -> None:
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"message": "profile-type required"})
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ValueError, match="profile-type required"):
            asyncio.run(render(query="bad", start_unix=1000.0, end_unix=2000.0))
