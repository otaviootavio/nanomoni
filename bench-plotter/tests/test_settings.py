"""Tests for settings module."""

import os
from unittest.mock import patch


from bench_plotter.settings import prometheus_base_url, web_port


class TestPrometheusBaseUrl:
    """Test Prometheus base URL configuration."""

    def test_default_url(self) -> None:
        """Test default Prometheus URL."""
        with patch.dict(os.environ, {}, clear=True):
            assert prometheus_base_url() == "http://127.0.0.1:9090"

    def test_custom_url(self) -> None:
        """Test custom Prometheus URL from environment."""
        custom_url = "http://prometheus.example.com:8080"
        with patch.dict(os.environ, {"PROMETHEUS_URL": custom_url}):
            assert prometheus_base_url() == custom_url

    def test_url_trailing_slash(self) -> None:
        """Test that trailing slash is removed."""
        url_with_slash = "http://prometheus.example.com:8080/"
        with patch.dict(os.environ, {"PROMETHEUS_URL": url_with_slash}):
            assert prometheus_base_url() == "http://prometheus.example.com:8080"

    def test_url_with_path(self) -> None:
        """Test URL with path preserves path."""
        url_with_path = "http://prometheus.example.com:8080/prometheus"
        with patch.dict(os.environ, {"PROMETHEUS_URL": url_with_path}):
            assert prometheus_base_url() == url_with_path


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


class TestEnvFileLoading:
    """Test .env file loading functionality."""

    def test_env_file_loading(self) -> None:
        """Test that env vars set by a .env file are picked up."""
        # dotenv loading happens at module import time, so test the behaviour
        # by patching os.environ directly (same effect as a loaded .env).
        with patch.dict(
            os.environ,
            {
                "PROMETHEUS_URL": "http://test.example.com:9090",
                "WEB_PORT": "9000",
            },
        ):
            from bench_plotter.settings import prometheus_base_url, web_port

            assert prometheus_base_url() == "http://test.example.com:9090"
            assert web_port() == 9000
