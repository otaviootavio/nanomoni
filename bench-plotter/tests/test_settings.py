"""Tests for settings module."""

import os
from unittest.mock import patch


from bench_plotter.settings import prometheus_base_url, pyroscope_base_url


class TestPrometheusBaseUrl:
    """The Prometheus base URL is intentionally hardcoded (no env / .env config)."""

    def test_default_url(self) -> None:
        """Returns the hardcoded URL when the environment is empty."""
        with patch.dict(os.environ, {}, clear=True):
            assert prometheus_base_url() == "http://127.0.0.1:9090"

    def test_ignores_env_override(self) -> None:
        """PROMETHEUS_URL in the environment is intentionally ignored."""
        with patch.dict(
            os.environ, {"PROMETHEUS_URL": "http://prometheus.example.com:8080"}
        ):
            assert prometheus_base_url() == "http://127.0.0.1:9090"


class TestPyroscopeBaseUrl:
    """The Pyroscope base URL is intentionally hardcoded, same as Prometheus's."""

    def test_default_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert pyroscope_base_url() == "http://127.0.0.1:4040"
