"""Tests for the steady-state latency transform (ECDF / violin / stats table)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from bench_plotter.pipeline.latency_transform import (
    _reduce_box_stats,
    _reduce_dists,
    transform_latency_box,
    transform_latency_dist,
)
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


def _quantile_payload(value: float) -> Dict[str, Any]:
    """Flat histogram_quantile series that survives steady_state_samples."""
    return {
        "data": {
            "result": [
                {
                    "metric": {},
                    "values": [[float(i) * 10, str(value)] for i in range(8)],
                }
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


class TestReduceBoxStats:
    def test_single_pass_through(self) -> None:
        stats = [
            {
                "label": "signature",
                "whislo": 1.0,
                "q1": 2.0,
                "med": 3.0,
                "q3": 4.0,
                "whishi": 5.0,
            }
        ]
        assert _reduce_box_stats(stats) == stats

    def test_averages_repeats_of_same_mode(self) -> None:
        stats = [
            {
                "label": "signature",
                "whislo": 1.0,
                "q1": 2.0,
                "med": 3.0,
                "q3": 4.0,
                "whishi": 5.0,
            },
            {
                "label": "signature",
                "whislo": 3.0,
                "q1": 4.0,
                "med": 5.0,
                "q3": 6.0,
                "whishi": 7.0,
            },
            {
                "label": "paytree",
                "whislo": 10.0,
                "q1": 11.0,
                "med": 12.0,
                "q3": 13.0,
                "whishi": 14.0,
            },
        ]
        reduced = _reduce_box_stats(stats)
        assert len(reduced) == 2
        by_label = {s["label"]: s for s in reduced}
        assert by_label["signature"]["med"] == pytest.approx(4.0)
        assert by_label["signature"]["whislo"] == pytest.approx(2.0)
        assert by_label["signature"]["whishi"] == pytest.approx(6.0)
        assert by_label["paytree"]["med"] == pytest.approx(12.0)


class TestReduceDists:
    def test_averages_cum_fraction_across_repeats(self) -> None:
        dists = [
            {"label": "signature", "edges": [1.0, 2.0], "cum_fraction": [0.4, 1.0]},
            {"label": "signature", "edges": [1.0, 2.0], "cum_fraction": [0.6, 1.0]},
            {"label": "paytree", "edges": [1.0, 2.0], "cum_fraction": [0.5, 1.0]},
        ]
        reduced = _reduce_dists(dists)
        assert len(reduced) == 2
        by_label = {d["label"]: d for d in reduced}
        assert by_label["signature"]["cum_fraction"] == pytest.approx([0.5, 1.0])
        assert by_label["paytree"]["cum_fraction"] == pytest.approx([0.5, 1.0])


class TestLatencyBoxRepeatCollapse:
    def test_repeated_modes_collapse_to_one_box(self) -> None:
        quantiles = [0.05, 0.25, 0.50, 0.75, 0.95]
        entries = []
        cache: ResultCache = {}
        # Two signature repeats with different medians (3 vs 5 -> mean 4),
        # plus one paytree.
        for mode, base, start in (
            ("signature", 1.0, 0.0),
            ("signature", 3.0, 100.0),
            ("paytree", 10.0, 200.0),
        ):
            q_specs = {
                q: QuerySpec(f"{mode}-{q}-{start}", start, start + 10.0)
                for q in quantiles
            }
            for q, spec in q_specs.items():
                # whislo=base, q1=base+1, ..., whishi=base+4
                cache[spec] = _quantile_payload(base + quantiles.index(q))
            entries.append({"mode": mode, "quantile_specs": q_specs})

        job = PlotJob(
            kind="latency_box",
            title="Vendor Payment Latency (steady-state)",
            output_path="box.png",
            section="tps_metrics",
            specs=list(cache.keys()),
            params={"entries": entries},
        )
        tasks = transform_latency_box(job, cache)
        assert len(tasks) == 1
        stats = tasks[0].kwargs["stats"]
        assert len(stats) == 2
        by_label = {s["label"]: s for s in stats}
        assert by_label["signature"]["med"] == pytest.approx(4.0)  # mean of 3 and 5
        assert by_label["paytree"]["med"] == pytest.approx(12.0)


class TestLatencyDistRepeatCollapse:
    def test_repeated_modes_collapse_to_one_ecdf(self) -> None:
        specs = [
            QuerySpec("sig-0", 0.0, 10.0),
            QuerySpec("sig-1", 20.0, 30.0),
            QuerySpec("pt-0", 40.0, 50.0),
        ]
        cache: ResultCache = {
            specs[0]: _bucket_payload({"10": 4.0, "20": 10.0, "+Inf": 10.0}),
            specs[1]: _bucket_payload({"10": 6.0, "20": 10.0, "+Inf": 10.0}),
            specs[2]: _bucket_payload({"10": 5.0, "20": 10.0, "+Inf": 10.0}),
        }
        job = PlotJob(
            kind="latency_dist",
            title="Vendor Payment Latency",
            output_path="ecdf.png",
            section="tps_metrics",
            specs=specs,
            params={
                "entries": [
                    {"mode": "signature", "spec": specs[0]},
                    {"mode": "signature", "spec": specs[1]},
                    {"mode": "paytree", "spec": specs[2]},
                ],
                "ecdf_path": "ecdf.png",
                "violin_path": "violin.png",
                "stats_path": "stats.png",
            },
        )
        tasks = transform_latency_dist(job, cache)
        ecdf = next(t for t in tasks if t.fn_name == "bucket_ecdf")
        dists = ecdf.kwargs["dists"]
        assert len(dists) == 2
        labels = {d["label"] for d in dists}
        assert labels == {"signature", "paytree"}
        stats = next(t for t in tasks if t.fn_name == "stats_table")
        assert len(stats.kwargs["rows"]) == 2
