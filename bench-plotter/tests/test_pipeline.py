"""Unit tests for the pipeline package (plan / fetch / draw registry / model)."""

import os
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from bench_plotter.metric_queries import get_charts_for_modes
from bench_plotter.draw_worker import DRAW_REGISTRY, run_draw_task
from bench_plotter.pipeline.model import DrawTask, PlotJob, QuerySpec
from bench_plotter.pipeline.plan import build_plan
from bench_plotter.pipeline.fetch import _unique_specs


def _intervals(modes: List[str], tps: Optional[int] = None) -> List[Dict[str, Any]]:
    out = []
    for i, mode in enumerate(modes):
        start = 1_000_000 + i * 1000
        interval: Dict[str, Any] = {
            "mode": mode,
            "status": "success",
            "prometheus_timestamps": {"start_ms": start, "finish_ms": start + 600},
        }
        if tps is not None:
            interval["tps"] = tps
        out.append(interval)
    return out


def _plan_paths(modes: List[str], tps: Optional[int] = None) -> set:
    """All figure output paths the plan implies, expanding multi-output jobs."""
    intervals = _intervals(modes, tps)
    charts = get_charts_for_modes(set(modes))
    jobs = build_plan(intervals, charts, output_dir="plots")
    paths = set()
    for job in jobs:
        rel = os.path.relpath(job.output_path, "plots")
        paths.add(rel)
        if job.kind == "steady_state":
            for key in ("ecdf_path", "violin_path"):
                paths.add(os.path.relpath(job.params[key], "plots"))
        if job.kind == "latency_dist":
            for key in ("ecdf_path", "violin_path", "stats_path"):
                paths.add(os.path.relpath(job.params[key], "plots"))
    return paths


PAYWORD_CONTRACT = {
    "client_resources/client_cpu_usage_cores.png",
    "client_resources/client_cpu_usage_cores_boxplot.png",
    "client_resources/client_cpu_usage_cores_ecdf.png",
    "client_resources/client_cpu_usage_cores_violin.png",
    "client_resources/client_memory_usage_mib.png",
    "client_resources/client_network_kib_s_input.png",
    "client_resources/client_network_kib_s_input_boxplot.png",
    "client_resources/client_network_kib_s_input_ecdf.png",
    "client_resources/client_network_kib_s_input_violin.png",
    "client_resources/client_network_kib_s_output.png",
    "client_resources/client_network_kib_s_output_boxplot.png",
    "client_resources/client_network_kib_s_output_ecdf.png",
    "client_resources/client_network_kib_s_output_violin.png",
    "issuer_resources/issuer_cpu_usage_cores.png",
    "issuer_resources/issuer_memory_usage_mib.png",
    "issuer_resources/issuer_network_kib_s_input.png",
    "issuer_resources/issuer_network_kib_s_output.png",
    "issuer_resources/issuer_redis_cpu_usage_cores_redis_issuer_cpu.png",
    "issuer_resources/issuer_redis_memory_usage_mib_redis_issuer_memory.png",
    "vendor_resources/vendor_cpu_usage_cores.png",
    "vendor_resources/vendor_cpu_usage_cores_boxplot.png",
    "vendor_resources/vendor_cpu_usage_cores_ecdf.png",
    "vendor_resources/vendor_cpu_usage_cores_violin.png",
    "vendor_resources/vendor_memory_usage_mib.png",
    "vendor_resources/vendor_network_kib_s_input.png",
    "vendor_resources/vendor_network_kib_s_input_boxplot.png",
    "vendor_resources/vendor_network_kib_s_input_ecdf.png",
    "vendor_resources/vendor_network_kib_s_input_violin.png",
    "vendor_resources/vendor_network_kib_s_output.png",
    "vendor_resources/vendor_network_kib_s_output_boxplot.png",
    "vendor_resources/vendor_network_kib_s_output_ecdf.png",
    "vendor_resources/vendor_network_kib_s_output_violin.png",
    "vendor_resources/vendor_redis_cpu_usage_cores_redis_vendor_cpu.png",
    "vendor_resources/vendor_redis_memory_usage_mib_redis_vendor_memory.png",
    "tps_metrics/vendor_payment_tps_success_payword.png",
    "tps_metrics/vendor_payment_duration_quantiles_ms_payword_p50.png",
    "tps_metrics/vendor_payment_duration_quantiles_ms_payword_p95.png",
    "tps_metrics/vendor_payment_duration_quantiles_ms_payword_p99.png",
    "tps_metrics/vendor_payment_latency_boxplot.png",
    "tps_metrics/vendor_payment_latency_ecdf.png",
    "tps_metrics/vendor_payment_latency_violin.png",
    "tps_metrics/vendor_payment_latency_stats.png",
}

# Dividing a rate by the payment rate that drove it needs the run's tps, which
# only a sweep-built plan carries.
PER_PAYMENT_PATH = "client_resources/client_network_kib_s_output_per_payment.png"
PER_PAYMENT_BAR_PATH = (
    "client_resources/client_network_kib_s_output_per_payment_bar.png"
)


class TestBuildPlan:
    def test_payword_only_path_set(self) -> None:
        assert _plan_paths(["payword"]) == PAYWORD_CONTRACT

    def test_per_payment_table_only_when_intervals_carry_tps(self) -> None:
        assert PER_PAYMENT_PATH not in _plan_paths(["payword"])
        assert PER_PAYMENT_PATH in _plan_paths(["payword"], tps=256)

    def test_per_payment_bar_only_when_intervals_carry_tps(self) -> None:
        assert PER_PAYMENT_BAR_PATH not in _plan_paths(["payword"])
        assert PER_PAYMENT_BAR_PATH in _plan_paths(["payword"], tps=256)

    def test_only_present_modes_are_queried(self) -> None:
        # A payword-only plan must not reference other modes' metrics.
        intervals = _intervals(["payword"])
        charts = get_charts_for_modes({"payword"})
        jobs = build_plan(intervals, charts, output_dir="plots")
        exprs = " ".join(spec.expr for job in jobs for spec in job.specs)
        assert "paytree_" not in exprs
        assert "payword_" in exprs

    def test_multi_mode_groups_tps_by_quantile(self) -> None:
        paths = _plan_paths(["signature", "payword", "paytree"])
        # Grouped-TPS combines modes into one figure per quantile (no _payword suffix).
        assert "tps_metrics/vendor_payment_duration_quantiles_ms_p99.png" in paths
        assert "tps_metrics/vendor_payment_tps_success.png" in paths

    def test_grouped_tps_series_count_matches_modes(self) -> None:
        # Regression: each grouped-TPS quantile figure must resolve exactly one
        # series per mode (one interval each), not mode_count x interval_count.
        # A mode-specific expr must only be queried against its own mode's
        # window, so 3 modes with 1 interval each -> 3 series, not 9.
        modes = ["signature", "payword", "paytree"]
        intervals = _intervals(modes)
        charts = get_charts_for_modes(set(modes))
        jobs = build_plan(intervals, charts, output_dir="plots")

        for stem in (
            "vendor_payment_duration_quantiles_ms_p99",
            "vendor_payment_tps_success",
        ):
            target = f"plots/tps_metrics/{stem}.png"
            job = next(j for j in jobs if j.output_path == target)
            series = job.params["series"]
            assert len(series) == len(modes)
            assert len(job.specs) == len(modes)
            assert sorted(s["label"] for s in series) == sorted(modes)


class TestFetchDedup:
    def test_identical_specs_collapse(self) -> None:
        s1 = QuerySpec("up", 1.0, 2.0)
        s2 = QuerySpec("up", 1.0, 2.0)  # same fields -> same key
        s3 = QuerySpec("up", 1.0, 3.0)  # different window

        job = PlotJob(
            kind="overlay",
            title="t",
            output_path="x.png",
            section="s",
            specs=[s1, s2, s3],
        )
        unique = _unique_specs([job])
        assert len(unique) == 2
        assert s1 in unique and s3 in unique


class TestDrawContract:
    def test_all_registry_names_used_by_plan_resolve(self) -> None:
        # Every fn_name a job could emit must exist in the worker registry.
        expected_fns = {
            "line_multi",
            "steady_state_box",
            "ecdf",
            "violin",
            "precomputed_box",
            "bucket_ecdf",
            "sweep_line",
            "stats_table",
        }
        assert expected_fns <= set(DRAW_REGISTRY)

    def test_draw_task_is_picklable(self) -> None:
        task = DrawTask(
            fn_name="line_multi",
            output_path="/tmp/x.png",
            kwargs={
                "series_list": [{"timestamps": [1.0], "values": [2.0]}],
                "title": "t",
            },
        )
        restored = pickle.loads(pickle.dumps(task))
        assert restored.fn_name == "line_multi"
        assert restored.kwargs["title"] == "t"

    def test_query_spec_is_hashable_and_picklable(self) -> None:
        spec = QuerySpec("up", 1.0, 2.0, step="15s")
        assert pickle.loads(pickle.dumps(spec)) == spec
        assert hash(spec) == hash(QuerySpec("up", 1.0, 2.0, step="15s"))


class TestRunDrawTask:
    def test_noop_render_removes_stale_and_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A renderer that writes nothing must not report a leftover PNG as fresh.
        stale = tmp_path / "x.png"
        stale.write_bytes(b"old")

        def _noop(output_path: str, **kwargs: Any) -> None:
            return None

        monkeypatch.setitem(DRAW_REGISTRY, "_noop", _noop)
        assert run_draw_task("_noop", str(stale), {}) is None
        assert not stale.exists()

    def test_render_that_writes_returns_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "y.png"

        def _write(output_path: str, **kwargs: Any) -> None:
            with open(output_path, "wb") as f:
                f.write(b"png")

        monkeypatch.setitem(DRAW_REGISTRY, "_write", _write)
        assert run_draw_task("_write", str(out), {}) == str(out)
        assert out.exists()


class TestRepeatCollapseInTransform:
    """Repeated intervals of the same mode must collapse to one series/box."""

    def test_overlay_collapses_same_mode_repeats_to_one_series(self) -> None:
        from bench_plotter.pipeline.transform import _series_list

        runs = [
            {
                "interval_mode": "signature",
                "timestamps": [100.0, 101.0, 102.0],
                "values": [1.0, 1.0, 1.0],
            },
            {
                "interval_mode": "signature",
                "timestamps": [200.0, 201.0, 202.0],
                "values": [3.0, 3.0, 3.0],
            },
            {
                "interval_mode": "paytree",
                "timestamps": [300.0, 301.0, 302.0],
                "values": [5.0, 5.0, 5.0],
            },
        ]
        series = _series_list(runs)
        assert len(series) == 2
        by_label = {s["label"]: s for s in series}
        assert by_label["signature"]["values"] == pytest.approx([2.0, 2.0, 2.0])
        assert "values_low" in by_label["signature"]
        assert "values_high" in by_label["signature"]
        assert by_label["paytree"]["values"] == [5.0, 5.0, 5.0]
        assert "values_low" not in by_label["paytree"]

    def test_steady_state_pools_same_mode_repeats_into_one_box(self) -> None:
        from bench_plotter.pipeline.steady_state_transform import (
            _pool_repeats_by_mode,
            transform_steady_state,
        )

        # Flat plateaus so steady_state_samples keeps the samples.
        runs = [
            {"interval_mode": "signature", "values": [10.0] * 10},
            {"interval_mode": "signature", "values": [12.0] * 10},
            {"interval_mode": "paytree", "values": [5.0] * 10},
        ]
        pooled = _pool_repeats_by_mode(runs)
        assert len(pooled) == 2
        by_mode = {r["interval_mode"]: r for r in pooled}
        assert len(by_mode["signature"]["values"]) == 20
        assert len(by_mode["paytree"]["values"]) == 10

        # End-to-end through transform_steady_state with a fake cache.
        from bench_plotter.pipeline.model import PlotJob, QuerySpec

        specs = [
            QuerySpec("up", 1.0, 2.0),
            QuerySpec("up", 3.0, 4.0),
            QuerySpec("up", 5.0, 6.0),
        ]

        def _payload(values: List[float]) -> Dict[str, Any]:
            # matrix_to_per_series_charts expects Prometheus matrix shape.
            return {
                "data": {
                    "result": [
                        {
                            "metric": {},
                            "values": [
                                [float(i), str(v)] for i, v in enumerate(values)
                            ],
                        }
                    ]
                }
            }

        series = [
            {"spec": specs[0], "label": "signature"},
            {"spec": specs[1], "label": "signature"},
            {"spec": specs[2], "label": "paytree"},
        ]
        cache = {
            specs[0]: _payload([10.0] * 10),
            specs[1]: _payload([12.0] * 10),
            specs[2]: _payload([5.0] * 10),
        }
        job = PlotJob(
            kind="steady_state",
            title="Vendor CPU Usage (Cores)",
            output_path="box.png",
            section="vendor_resources",
            specs=specs,
            params={
                "series": series,
                "unit_label": "Cores",
                "ecdf_path": "ecdf.png",
                "violin_path": "violin.png",
            },
        )
        tasks = transform_steady_state(job, cache)
        assert len(tasks) == 3
        box = next(t for t in tasks if t.fn_name == "steady_state_box")
        assert box.kwargs["trim"] is False
        assert len(box.kwargs["series_list"]) == 2
        modes = {s["interval_mode"] for s in box.kwargs["series_list"]}
        assert modes == {"signature", "paytree"}
        ecdf = next(t for t in tasks if t.fn_name == "ecdf")
        assert ecdf.kwargs["trim"] is False
        violin = next(t for t in tasks if t.fn_name == "violin")
        assert violin.kwargs["trim"] is False
