"""Integration tests for the full pipeline wiring.

These drive ``generate_plots_from_benchmark`` with the fetch stage stubbed
(canned Prometheus payloads) and the draw stage captured, so they exercise
plan -> transform -> draw wiring and the produced output-path set without a live
Prometheus or real rendering.
"""

import json
import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from bench_plotter.generate_plots import main
from bench_plotter.pipeline import generate_plots_from_benchmark


PAYWORD_ONLY = [
    {
        "mode": "payword",
        "status": "success",
        "prometheus_timestamps": {"start_ms": 1000000, "finish_ms": 1000600},
    }
]


def _canned_range_payload() -> Dict[str, Any]:
    """A flat, non-zero range series that survives steady-state filtering."""
    values = [[1000.0 + i * 15, "1.0"] for i in range(10)]
    return {"data": {"result": [{"metric": {"__name__": "m"}, "values": values}]}}


def _stub_fetch(jobs):
    cache = {spec: _canned_range_payload() for job in jobs for spec in job.specs}
    return cache, []


def _run_capturing_draw(intervals: List[Dict[str, Any]]):
    """Run the pipeline; return the set of output paths handed to the draw stage."""
    captured: List[str] = []

    def _capture_draw(tasks, workers=None, parallel=True):
        captured.extend(t.output_path for t in tasks)
        return [t.output_path for t in tasks], []

    with tempfile.TemporaryDirectory() as tmp:
        intervals_path = os.path.join(tmp, "timing.json")
        with open(intervals_path, "w") as f:
            json.dump(intervals, f)
        out = os.path.join(tmp, "plots")
        with patch("bench_plotter.pipeline.orchestrator.fetch_all", _stub_fetch):
            with patch("bench_plotter.pipeline.orchestrator.draw_all", _capture_draw):
                generate_plots_from_benchmark(intervals_path, output_dir=out)
        rel = {os.path.relpath(p, out) for p in captured}
    return rel


class TestPipelineWiring:
    def test_payword_only_produces_expected_paths(self) -> None:
        paths = _run_capturing_draw(PAYWORD_ONLY)

        # Resource timeseries for every service.
        assert "vendor_resources/vendor_cpu_usage_cores.png" in paths
        assert "issuer_resources/issuer_memory_usage_mib.png" in paths
        assert "client_resources/client_network_kib_s_input.png" in paths
        # Steady-state companions for vendor/client CPU + network.
        assert "vendor_resources/vendor_cpu_usage_cores_boxplot.png" in paths
        assert "client_resources/client_network_kib_s_output_violin.png" in paths
        # TPS + per-quantile latency.
        assert "tps_metrics/vendor_payment_tps_success_payword.png" in paths
        assert (
            "tps_metrics/vendor_payment_duration_quantiles_ms_payword_p99.png" in paths
        )
        # Steady-state latency suite.
        assert "tps_metrics/vendor_payment_latency_boxplot.png" in paths

        # Only payword ran, so no signature/paytree series were queried.
        assert not any("signature" in p or "paytree" in p for p in paths)

    def test_no_successful_intervals_produces_nothing(self) -> None:
        failed = [{"mode": "payword", "status": "failed"}]
        assert _run_capturing_draw(failed) == set()


class TestCliMissingFile:
    def test_main_exits_on_missing_file(self) -> None:
        with patch("sys.argv", ["generate_plots", "/nonexistent/timing.json"]):
            with pytest.raises(SystemExit):
                main()
