"""Tests for the steady-state latency transform (ECDF / violin / stats table)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from bench_plotter.pipeline.latency_transform import transform_latency_dist
from bench_plotter.pipeline.model import PlotJob, QuerySpec, ResultCache


def _bucket_payload(cumulative_by_le: Dict[str, float]) -> Dict[str, Any]:
    """A bucket-rate matrix payload, flat over the window so it survives trimming."""
    return {
        "data": {
            "result": [
                {
                    "metric": {"le": le},
                    "values": [[float(i) * 10, str(rate)] for i in range(8)],
                }
                for le, rate in cumulative_by_le.items()
            ]
        }
    }


def _job(spec: QuerySpec) -> PlotJob:
    return PlotJob(
        kind="latency_dist",
        title="Vendor Payment Latency",
        output_path="plots/tps_metrics/vendor_payment_latency_ecdf.png",
        section="tps_metrics",
        specs=[spec],
        params={
            "entries": [{"mode": "payword", "spec": spec}],
            "ecdf_path": "plots/tps_metrics/vendor_payment_latency_ecdf.png",
            "violin_path": "plots/tps_metrics/vendor_payment_latency_violin.png",
            "stats_path": "plots/tps_metrics/vendor_payment_latency_stats.png",
        },
    )


def _tasks(cumulative_by_le: Dict[str, float]) -> List[Any]:
    spec = QuerySpec("buckets", 0.0, 100.0)
    cache: ResultCache = {spec: _bucket_payload(cumulative_by_le)}
    return transform_latency_dist(_job(spec), cache)


class TestLatencyStatsTable:
    def test_emits_mean_stddev_and_quantiles_per_mode(self) -> None:
        # Half the observations in (0, 10] and half in (10, 20]: bucket midpoints
        # 5 and 15 give mean 10 and stddev 5, and the median sits on the boundary.
        tasks = _tasks({"10": 5.0, "20": 10.0, "+Inf": 10.0})
        stats = next(t for t in tasks if t.fn_name == "stats_table")

        assert stats.output_path.endswith("vendor_payment_latency_stats.png")
        assert stats.kwargs["col_labels"] == [
            "mode",
            "mean_ms",
            "stddev_ms",
            "p50_ms",
            "p95_ms",
        ]
        (row,) = stats.kwargs["rows"]
        mode, mean, stddev, p50, p95 = row
        assert mode == "payword"
        assert mean == pytest.approx(10.0)
        assert stddev == pytest.approx(5.0)
        assert p50 == pytest.approx(10.0)
        assert p95 == pytest.approx(19.0)

    def test_ecdf_and_violin_are_still_emitted(self) -> None:
        fns = {t.fn_name for t in _tasks({"10": 5.0, "20": 10.0, "+Inf": 10.0})}
        assert fns == {"bucket_ecdf", "violin", "stats_table"}

    def test_no_buckets_yields_no_tasks(self) -> None:
        assert _tasks({}) == []
