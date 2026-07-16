"""Tests for settings module."""

import os
from unittest.mock import patch


from bench_plotter.settings import prometheus_base_url, web_port


class TestPrometheusBaseUrl:
    """The Prometheus base URL is intentionally hardcoded (no env / .env config)."""

    def test_default_url(self) -> None:
        """Returns the hardcoded URL when the environment is empty."""
        with patch.dict(os.environ, {}, clear=True):
            assert prometheus_base_url() == "http://127.0.0.1:9090"

    def test_ignores_env_override(self) -> None:
        """PROMETHEUS_URL in the environment is intentionally ignored."""
        with patch.dict(os.environ, {"PROMETHEUS_URL": "http://prometheus.example.com:8080"}):
            assert prometheus_base_url() == "http://127.0.0.1:9090"


class TestWebPort:
    """Test web port configuration."""

    def test_default_port(self) -> None:
        """Test default web port."""
        with patch.dict(os.environ, {}, clear=True):
            assert web_port() == 3030

    def test_custom_port(self) -> None:
        """Test custom web port from environment."""
        with patch.dict(os.environ, {"WEB_PORT": "8080"}):
            assert web_port() == 8080

    def test_invalid_port_string(self) -> None:
        """Test invalid port string falls back to default."""
        with patch.dict(os.environ, {"WEB_PORT": "invalid"}):
            assert web_port() == 3030

    def test_port_out_of_range_low(self) -> None:
        """Test port below valid range."""
        with patch.dict(os.environ, {"WEB_PORT": "0"}):
            assert web_port() == 1  # Minimum valid port

    def test_port_out_of_range_high(self) -> None:
        """Test port above valid range."""
        with patch.dict(os.environ, {"WEB_PORT": "70000"}):
            assert web_port() == 65535  # Maximum valid port

    def test_edge_case_ports(self) -> None:
        """Test edge case valid ports."""
        with patch.dict(os.environ, {"WEB_PORT": "1"}):
            assert web_port() == 1

        with patch.dict(os.environ, {"WEB_PORT": "65535"}):
            assert web_port() == 65535
