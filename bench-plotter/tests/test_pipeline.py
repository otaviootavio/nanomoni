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


class TestBuildPlan:
    def test_payword_only_path_set(self) -> None:
        assert _plan_paths(["payword"]) == PAYWORD_CONTRACT

    def test_per_payment_table_only_when_intervals_carry_tps(self) -> None:
        assert PER_PAYMENT_PATH not in _plan_paths(["payword"])
        assert PER_PAYMENT_PATH in _plan_paths(["payword"], tps=256)

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
