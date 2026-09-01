"""Unit tests for the TPS-sweep plotting helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from bench_plotter.draw_worker import DRAW_REGISTRY
from bench_plotter.plotting.common import PALETTE
from bench_plotter.plotting.sweep_renderers import (
    create_identity_comparison_plot,
    create_sweep_line_plot,
)
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.sweep import aggregate as sweep_aggregate
from bench_plotter.sweep.aggregate import (
    _fetch_run_metrics,
    _latency_series,
    _mode_style,
    _series_by_mode,
    build_aggregate_draw_tasks,
)
from bench_plotter.sweep.runner import (
    config_dirname,
    export_raw_run_table,
    group_runs_by_config,
    generate_sweep_plots,
)


def _matrix_payload(values: list[tuple[float, float]]) -> Dict[str, Any]:
    """Build a query_range-shaped payload from (timestamp, value) pairs."""
    return {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"__name__": "series"},
                    "values": [[t, str(v)] for t, v in values],
                }
            ]
        },
    }


def _run(
    mode: str,
    tps: int,
    total: int,
    *,
    status: str = "success",
    start_ms: int = 1_000_000,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "tps": tps,
        "total_requests": total,
        "status": status,
        "prometheus_timestamps": {
            "start_ms": start_ms,
            "finish_ms": start_ms + 600_000,
        },
    }


class TestGroupRunsByConfig:
    def test_groups_by_tps_and_total(self) -> None:
        runs = [
            _run("signature", 16, 9600),
            _run("paytree", 16, 9600),
            _run("signature", 32, 19200),
            _run("payword", 16, 9600),
        ]
        groups = group_runs_by_config(runs)
        assert set(groups.keys()) == {(16, 9600), (32, 19200)}
        assert [r["mode"] for r in groups[(16, 9600)]] == [
            "signature",
            "paytree",
            "payword",
        ]
        assert [r["mode"] for r in groups[(32, 19200)]] == ["signature"]

    def test_skips_runs_missing_tps_or_total(self) -> None:
        runs = [
            _run("signature", 16, 9600),
            {"mode": "paytree", "status": "success"},
            {"mode": "payword", "tps": 32, "status": "success"},
        ]
        groups = group_runs_by_config(runs)
        assert list(groups.keys()) == [(16, 9600)]


class TestConfigDirname:
    def test_format(self) -> None:
        assert config_dirname(64, 38400) == "tps64_req38400"


class TestSteadyStateReduce:
    def test_plateau_mean_and_p95(self) -> None:
        # Ramp + plateau + drain; steady_state_samples keeps the plateau.
        values = [0.1, 0.2, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.1]
        samples = steady_state_samples(values)
        assert samples
        assert all(0.8 <= v <= 1.2 for v in samples)


class TestMcpuPerPaymentUsesAchievedTps:
    def test_divides_by_achieved_not_target_when_client_falls_short(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The saturation sweep found that a client asked for 1024 TPS can settle
        # at ~512 while still exiting 0. Dividing vendor CPU by the 1024 target
        # would then understate mcpu_per_payment by ~2x -- and by a different
        # factor per mode, distorting the cross-mode comparison this chart makes.
        vendor_cpu = 0.5  # cores
        achieved = 512.0  # real TPS, half of the 1024 target

        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_cpu_usage_seconds_total" in query and "redis" not in query:
                return _matrix_payload([(0.0, vendor_cpu)] * 6)
            if "requests_total" in query:
                # Flat plateau covering the whole window -> sustained_rate == achieved.
                return _matrix_payload([(float(i * 5), achieved) for i in range(8)])
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        run = {
            "mode": "signature",
            "tps": 1024,
            "repeat": 2,
            "prometheus_timestamps": {"start_ms": 1_000, "finish_ms": 46_000},
        }

        async def _run() -> Any:
            # The semaphore must be constructed inside the coroutine asyncio.run
            # drives: built as a bare argument, Semaphore.__init__ binds to the
            # current event loop eagerly (Python 3.9), which doesn't exist yet.
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_run())

        assert result is not None
        expected_mcpu = (vendor_cpu / achieved) * 1000.0
        wrong_mcpu_if_using_target = (vendor_cpu / 1024.0) * 1000.0
        assert result["mcpu_per_payment"] == pytest.approx(expected_mcpu)
        assert result["mcpu_per_payment"] != pytest.approx(wrong_mcpu_if_using_target)
        # vs-TPS charts and per-payment denominators must see the measured rate,
        # not the configured target, when Prometheus can resolve it.
        assert result["achieved_tps"] == pytest.approx(achieved)
        assert result["tps"] == 1024.0  # target preserved for grouping / folders
        # Join key for the per-run metrics CSV (see export_raw_run_table).
        assert result["repeat"] == 2

    def test_falls_back_to_target_when_achieved_tps_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vendor_cpu = 0.1

        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_cpu_usage_seconds_total" in query and "redis" not in query:
                return _matrix_payload([(0.0, vendor_cpu)] * 6)
            # No payment traffic resolvable (e.g. Prometheus query failed).
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        run = {
            "mode": "signature",
            "tps": 64,
            "prometheus_timestamps": {"start_ms": 1_000, "finish_ms": 46_000},
        }

        async def _run() -> Any:
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_run())

        assert result is not None
        assert result["mcpu_per_payment"] == pytest.approx((vendor_cpu / 64.0) * 1000.0)
        # No measured rate -> fall back to the configured target for both the
        # per-payment denominator and the vs-TPS x-axis value.
        assert result["achieved_tps"] == pytest.approx(64.0)
        assert result["payments_served"] is None
        assert result["payments_count"] is None  # no total_requests on this run either
        # Legacy / missing repeat must still land as None so the join key is
        # well-defined rather than KeyError'd away.
        assert result["repeat"] is None


class TestExportRawRunTable:
    """Per-run Prometheus + Pyroscope join written as all_runs.csv."""

    def test_merges_on_join_key_keeps_both_achieved_tps_drops_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_collect_scalars(
            runs: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            return [
                {
                    "mode": "signature",
                    "tps": 250.0,
                    "total_requests": 30000,
                    "repeat": 0,
                    "achieved_tps": 248.0,
                    "latency_p50": 0.7,
                    "mcpu_per_payment": 1.2,
                },
                {
                    "mode": "signature",
                    "tps": 250.0,
                    "total_requests": 30000,
                    "repeat": 1,
                    "achieved_tps": 249.0,
                    "latency_p50": 0.71,
                    "mcpu_per_payment": 1.1,
                },
            ]

        async def fake_collect_profiles(
            runs: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            return [
                {
                    "mode": "signature",
                    "tps": 250.0,
                    "total_requests": 30000,
                    "repeat": 0,
                    "achieved_tps": 247.5,
                    "crypto_ms_per_payment": 0.03,
                    "payload": {"huge": "flamebearer tree"},
                },
                # Profile-only row (no matching scalar) still lands in the CSV.
                {
                    "mode": "paytree",
                    "tps": 250.0,
                    "total_requests": 30000,
                    "repeat": 0,
                    "achieved_tps": 250.0,
                    "crypto_ms_per_payment": 0.04,
                    "payload": {"ignored": True},
                },
            ]

        monkeypatch.setattr(
            "bench_plotter.sweep.runner._collect_scalars", fake_collect_scalars
        )
        monkeypatch.setattr(
            "bench_plotter.sweep.runner._collect_profiles", fake_collect_profiles
        )

        csv_path = export_raw_run_table(
            [_run("signature", 250, 30000), _run("paytree", 250, 30000)],
            output_dir=str(tmp_path),
        )
        assert csv_path == str(tmp_path / "all_runs.csv")
        assert Path(csv_path).exists()

        import pandas as pd

        df = pd.read_csv(csv_path)
        assert len(df) == 3
        # Flamebearer payload must not leak into the tabular export.
        assert "payload" not in df.columns

        sig0 = df[(df["mode"] == "signature") & (df["repeat"] == 0)].iloc[0]
        assert sig0["achieved_tps"] == pytest.approx(248.0)
        assert sig0["profile_achieved_tps"] == pytest.approx(247.5)
        assert sig0["latency_p50"] == pytest.approx(0.7)
        assert sig0["crypto_ms_per_payment"] == pytest.approx(0.03)

        # Scalar-only repeat (no matching profile) keeps its Prometheus rate
        # and has no profile_achieved_tps overwrite.
        sig1 = df[(df["mode"] == "signature") & (df["repeat"] == 1)].iloc[0]
        assert sig1["achieved_tps"] == pytest.approx(249.0)
        assert sig1["mcpu_per_payment"] == pytest.approx(1.1)

        # Profile-only mode still appears, under the renamed rate column.
        paytree = df[df["mode"] == "paytree"].iloc[0]
        assert paytree["profile_achieved_tps"] == pytest.approx(250.0)
        assert paytree["crypto_ms_per_payment"] == pytest.approx(0.04)

    def test_returns_none_on_empty_runs(self, tmp_path: Path) -> None:
        assert export_raw_run_table([], output_dir=str(tmp_path)) is None
        assert not (tmp_path / "all_runs.csv").exists()

    def test_returns_none_when_collectors_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            raise RuntimeError("prometheus down")

        monkeypatch.setattr("bench_plotter.sweep.runner._collect_scalars", boom)
        assert (
            export_raw_run_table(
                [_run("signature", 250, 30000)], output_dir=str(tmp_path)
            )
            is None
        )


class TestRedisMemoryUsesSettledNotPeak:
    """The delta must score the dataset a run leaves behind, not its teardown peak.

    paytree_first_opt settlement briefly pushes Redis RSS far above what it
    retains, for less than one cadvisor scrape. Reducing with max turned a flat
    ~423 bytes/payment into a 421..856 sawtooth across the 20260806 sweep.
    """

    # 5s steps starting at t=1s: flat baseline, a linear climb, one settlement
    # spike, then a 60s drain plateau. The spike falls inside the drain window,
    # so this also pins that the median shrugs off a lone outlier there.
    _VALUES = (
        [10.0] * 4 + [10.0 + 5.0 * i for i in range(1, 19)] + [260.0] + [100.0] * 12
    )

    @classmethod
    def _memory_run(
        cls, **extra: Any
    ) -> Tuple[Dict[str, Any], List[Tuple[float, float]]]:
        points = [(1.0 + i * 5.0, v) for i, v in enumerate(cls._VALUES)]
        run: Dict[str, Any] = {
            "mode": "paytree_first_opt",
            "tps": 256,
            "total_requests": 1000,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(points[-1][0] * 1_000),
            },
        }
        run.update(extra)
        return run, points

    def _collect(
        self,
        monkeypatch: pytest.MonkeyPatch,
        run: Dict[str, Any],
        points: List[Tuple[float, float]],
    ) -> Dict[str, Any]:
        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_memory_working_set_bytes" in query:
                return _matrix_payload(points)
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        async def _go() -> Any:
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_go())
        assert result is not None
        return result

    def test_settles_on_drain_plateau_ignoring_spike(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, points = self._memory_run(drain_sec=60)
        result = self._collect(monkeypatch, run, points)

        assert result["vendor_redis_memory_baseline_mib"] == pytest.approx(10.0)
        assert result["vendor_redis_memory_settled_mib"] == pytest.approx(100.0)
        assert result["vendor_redis_memory_delta_mib"] == pytest.approx(90.0)
        # The 260 spike would have scored 250 MiB -- nearly 3x the truth.
        assert result["vendor_redis_memory_delta_mib"] != pytest.approx(250.0)

    def test_falls_back_to_window_fraction_without_drain_sec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Timing files written before drain_sec existed must still avoid the peak.
        run, points = self._memory_run()
        result = self._collect(monkeypatch, run, points)
        assert result["vendor_redis_memory_delta_mib"] == pytest.approx(90.0)

    def test_delta_is_never_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Baseline is the floor over the whole window, tail included, so a run
        # that ends below where it started cannot produce a negative delta.
        points = [
            (1.0 + i * 5.0, v) for i, v in enumerate([50.0, 40.0, 30.0, 20.0] * 2)
        ]
        run = {
            "mode": "signature",
            "tps": 16,
            "total_requests": 100,
            "drain_sec": 20,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(points[-1][0] * 1_000),
            },
        }
        result = self._collect(monkeypatch, run, points)
        assert result["vendor_redis_memory_delta_mib"] >= 0.0


class TestPaymentsCountAndRedisBytesPerPayment:
    """payments_count comes from the vendor counter; redis bytes/payment uses it."""

    def test_divides_redis_delta_by_measured_payment_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Flat 10 MiB baseline, flat 20 MiB drain plateau -> delta = 10 MiB.
        # Vendor counter advances by 500 payments (not the configured 1000).
        mem_points = [(1.0 + i * 5.0, 10.0) for i in range(8)] + [
            (1.0 + (8 + i) * 5.0, 20.0) for i in range(12)
        ]
        served_start, served_end = 100.0, 600.0  # delta = 500

        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_memory_working_set_bytes" in query:
                return _matrix_payload(mem_points)
            if "rate(" in query:
                return _matrix_payload([(float(i * 5), 10.0) for i in range(8)])
            if "requests_total" in query or "payment" in query:
                return _matrix_payload([(0.0, served_start), (50.0, served_end)])
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        run = {
            "mode": "signature",
            "tps": 16,
            "total_requests": 1000,
            "drain_sec": 60,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(mem_points[-1][0] * 1_000),
            },
        }

        async def _go() -> Any:
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_go())
        assert result is not None
        assert result["payments_served"] == pytest.approx(500.0)
        assert result["payments_count"] == pytest.approx(500.0)
        expected = 10.0 * (1024.0 * 1024.0) / 500.0
        assert result["vendor_redis_memory_delta_bytes_per_payment"] == pytest.approx(
            expected
        )

    def test_falls_back_to_total_requests_when_counter_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Flat 5 -> flat 15 over a 60s drain: delta = 10 MiB; no counter data.
        mem_points = [(1.0 + i * 5.0, 5.0) for i in range(8)] + [
            (1.0 + (8 + i) * 5.0, 15.0) for i in range(12)
        ]

        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_memory_working_set_bytes" in query:
                return _matrix_payload(mem_points)
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        run = {
            "mode": "signature",
            "tps": 16,
            "total_requests": 200,
            "drain_sec": 60,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(mem_points[-1][0] * 1_000),
            },
        }

        async def _go() -> Any:
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_go())
        assert result is not None
        assert result["payments_served"] is None
        assert result["payments_count"] == 200
        expected = 10.0 * (1024.0 * 1024.0) / 200.0
        assert result["vendor_redis_memory_delta_bytes_per_payment"] == pytest.approx(
            expected
        )


class TestRedisMemoryGrowthRate:
    """The linear-fit slope ``m`` (MiB/s) computed alongside the delta."""

    def _collect(
        self,
        monkeypatch: pytest.MonkeyPatch,
        run: Dict[str, Any],
        points: List[Tuple[float, float]],
    ) -> Dict[str, Any]:
        async def fake_query_range(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_memory_working_set_bytes" in query:
                return _matrix_payload(points)
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range)

        async def _go() -> Any:
            return await _fetch_run_metrics(run, asyncio.Semaphore(1))

        result = asyncio.run(_go())
        assert result is not None
        return result

    def test_slope_matches_known_linear_climb(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Exactly 2 MiB/s: value = 10 + 2*elapsed_seconds, sampled every 5s.
        points = [(1.0 + i * 5.0, 10.0 + 2.0 * (i * 5.0)) for i in range(20)]
        run = {
            "mode": "paytree_first_opt",
            "tps": 256,
            "total_requests": 1000,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(points[-1][0] * 1_000),
            },
        }
        result = self._collect(monkeypatch, run, points)
        assert result["vendor_redis_memory_growth_rate_mib_per_s"] == pytest.approx(2.0)

    def test_flat_series_has_near_zero_slope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        points = [(1.0 + i * 5.0, 42.0) for i in range(10)]
        run = {
            "mode": "signature",
            "tps": 16,
            "total_requests": 100,
            "prometheus_timestamps": {
                "start_ms": 1_000,
                "finish_ms": int(points[-1][0] * 1_000),
            },
        }
        result = self._collect(monkeypatch, run, points)
        assert result["vendor_redis_memory_growth_rate_mib_per_s"] == pytest.approx(
            0.0, abs=1e-9
        )

    def test_no_points_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = {
            "mode": "signature",
            "tps": 16,
            "total_requests": 100,
            "prometheus_timestamps": {"start_ms": 1_000, "finish_ms": 61_000},
        }
        result = self._collect(monkeypatch, run, [])
        assert result["vendor_redis_memory_growth_rate_mib_per_s"] is None


class TestBuildAggregateDrawTasksGrowthRate:
    """The m-per-mode column chart and m-vs-TPS chart get wired into the plan."""

    def test_includes_growth_rate_charts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        points_by_mode = {
            "paytree_first_opt": [
                (1.0 + i * 5.0, 10.0 + 2.0 * (i * 5.0)) for i in range(10)
            ],
            "signature": [(1.0 + i * 5.0, 5.0) for i in range(10)],
        }
        runs = [
            _run("paytree_first_opt", 256, 1000),
            _run("signature", 256, 1000),
        ]
        # Patch query_range per-mode so each run's memory series differs.
        call_mode: Dict[str, Any] = {"current": None}

        async def fake_query_range_per_mode(
            *, query: str, start_unix: float, end_unix: float, step: str | None = None
        ) -> Dict[str, Any]:
            if "container_memory_working_set_bytes" in query:
                return _matrix_payload(points_by_mode[call_mode["current"]])
            return _matrix_payload([])

        monkeypatch.setattr(sweep_aggregate, "query_range", fake_query_range_per_mode)

        async def fake_collect_scalars(
            runs: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            results = []
            sem = asyncio.Semaphore(1)
            for run in runs:
                call_mode["current"] = run["mode"]
                results.append(await _fetch_run_metrics(run, sem))
            return [r for r in results if r is not None]

        monkeypatch.setattr(sweep_aggregate, "_collect_scalars", fake_collect_scalars)

        tasks = build_aggregate_draw_tasks(runs, "out")
        output_paths = {t.output_path for t in tasks}

        assert "out/vendor_redis_memory_growth_rate_vs_tps.png" in output_paths
        assert (
            "out/vendor_redis_memory_delta_bytes_per_payments_vs_tps.png"
            in output_paths
        )
        assert (
            "out/tps256_req1000/vendor_resources/vendor_redis_memory_growth_rate_bar.png"
            in output_paths
        )


class TestSweepLineRenderer:
    def test_sweep_line_in_registry(self) -> None:
        assert "sweep_line" in DRAW_REGISTRY

    def test_writes_png(self, tmp_path: Path) -> None:
        out = tmp_path / "sweep.png"
        create_sweep_line_plot(
            series_list=[
                {
                    "label": "signature p50",
                    "x_values": [16, 32, 64],
                    "y_values": [1.0, 1.5, 2.0],
                },
                {
                    "label": "payword p50",
                    "x_values": [16, 32, 64],
                    "y_values": [0.5, 0.7, 0.9],
                },
            ],
            title="Latency vs TPS",
            output_path=str(out),
            y_axis_label="Latency (ms)",
        )
        assert out.exists()
        assert out.stat().st_size > 0

    def test_empty_series_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.png"
        create_sweep_line_plot(series_list=[], output_path=str(out))
        assert not out.exists()

    def test_style_overrides_write_png(self, tmp_path: Path) -> None:
        out = tmp_path / "styled.png"
        create_sweep_line_plot(
            series_list=[
                {
                    "label": "paytree",
                    "x_values": [16, 32],
                    "y_values": [1.0, 0.8],
                    "color": "#2a78d6",
                    "linestyle": "-",
                    "marker": "o",
                },
            ],
            title="Latency p50 vs TPS",
            output_path=str(out),
            y_axis_label="Latency (ms)",
        )
        assert out.exists()
        assert out.stat().st_size > 0

    def test_x_true_log_writes_png(self, tmp_path: Path) -> None:
        out = tmp_path / "x_true_log.png"
        create_sweep_line_plot(
            series_list=[
                {
                    "label": "paytree",
                    "x_values": [4800, 9600, 19200, 38400],
                    "y_values": [2.0, 3.0, 5.0, 8.0],
                },
            ],
            title="Bytes per payment vs total payments",
            output_path=str(out),
            x_axis_label="Total payments",
            y_axis_label="Bytes / payment",
            x_log_base=2,
            x_true_log=True,
        )
        assert out.exists()
        assert out.stat().st_size > 0


class TestIdentityComparisonRenderer:
    def test_writes_png_and_stays_square_with_many_series(self, tmp_path: Path) -> None:
        # 5 series + the identity line is this chart's typical real-world
        # count; a single-row legend at that count once stretched the whole
        # (deliberately square) figure into a squashed wide rectangle -- the
        # legend must wrap instead, so the saved figure stays roughly square.
        series_list = [
            {
                "label": mode,
                "x_values": [16, 32, 64, 128, 256],
                "y_values": [v * (idx + 1) for v in (10, 20, 40, 80, 160)],
            }
            for idx, mode in enumerate(
                [
                    "paytree",
                    "paytree_child_pair",
                    "paytree_first_opt",
                    "payword",
                    "signature",
                ]
            )
        ]
        out = tmp_path / "identity.png"
        create_identity_comparison_plot(series_list, output_path=str(out))
        assert out.exists()

        from PIL import Image

        with Image.open(out) as img:
            width, height = img.size
        aspect = width / height
        assert 0.8 <= aspect <= 1.6, (
            f"expected a roughly square figure, got {width}x{height}"
        )

    def test_no_series_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "identity.png"
        create_identity_comparison_plot([], output_path=str(out))
        assert not out.exists()


class TestModeStyle:
    def test_known_modes_get_stable_palette_slots(self) -> None:
        # Slot = position in KNOWN_MODES, so every chart gives a mode the same hue.
        paytree = _mode_style("paytree")
        payword = _mode_style("payword")
        signature = _mode_style("signature")
        assert paytree["color"] == PALETTE[0]
        assert payword["color"] == PALETTE[4]
        assert signature["color"] == PALETTE[5]
        assert paytree["marker"] != payword["marker"]

    def test_series_by_mode_attaches_style(self) -> None:
        scalars = [
            {"mode": "paytree", "tps": 16.0, "vendor_cpu_mean": 0.02},
            {"mode": "paytree", "tps": 32.0, "vendor_cpu_mean": 0.04},
            {"mode": "signature", "tps": 16.0, "vendor_cpu_mean": 0.03},
        ]
        series = _series_by_mode(scalars, "vendor_cpu_mean")
        assert len(series) == 2
        by_label = {s["label"]: s for s in series}
        assert by_label["paytree"]["color"] == PALETTE[0]
        assert by_label["paytree"]["linestyle"] == "-"
        assert by_label["signature"]["color"] == PALETTE[5]

    def test_latency_series_p50_only(self) -> None:
        # vs-TPS charts now plot against achieved_tps (falls back to target when
        # the counter is unavailable); the fixture mirrors that contract.
        scalars = [
            {"mode": "paytree", "tps": 16.0, "achieved_tps": 16.0, "latency_p50": 0.5},
            {"mode": "paytree", "tps": 32.0, "achieved_tps": 32.0, "latency_p50": 0.4},
            {
                "mode": "signature",
                "tps": 16.0,
                "achieved_tps": 16.0,
                "latency_p50": 1.0,
            },
        ]
        series = _latency_series(scalars)
        assert len(series) == 2
        by_label = {s["label"]: s for s in series}
        assert by_label["paytree"]["y_values"] == [0.5, 0.4]
        assert "y_low" not in by_label["paytree"]
        assert by_label["paytree"]["color"] == PALETTE[0]
        assert by_label["signature"]["color"] == PALETTE[5]

    def test_series_by_mode_carries_low_high_bounds_when_present(self) -> None:
        # As added by bench_plotter.repeats.reduce_repeats when a point
        # averages several repeats.
        scalars = [
            {
                "mode": "paytree",
                "tps": 16.0,
                "vendor_cpu_mean": 0.03,
                "vendor_cpu_mean_low": 0.02,
                "vendor_cpu_mean_high": 0.04,
            },
            {
                "mode": "paytree",
                "tps": 32.0,
                "vendor_cpu_mean": 0.06,
                "vendor_cpu_mean_low": 0.05,
                "vendor_cpu_mean_high": 0.07,
            },
        ]
        series = _series_by_mode(scalars, "vendor_cpu_mean")
        assert len(series) == 1
        assert series[0]["y_low"] == [0.02, 0.05]
        assert series[0]["y_high"] == [0.04, 0.07]

    def test_series_by_mode_omits_bounds_when_absent(self) -> None:
        scalars = [
            {"mode": "paytree", "tps": 16.0, "vendor_cpu_mean": 0.03},
        ]
        series = _series_by_mode(scalars, "vendor_cpu_mean")
        assert "y_low" not in series[0]
        assert "y_high" not in series[0]


class TestGenerateSweepPlotsLoad:
    def test_object_shape_creates_timestamp_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        timing = tmp_path / "benchmark_timing.json"
        timing.write_text(
            json.dumps(
                {
                    "server_run_timestamp": "20260722_120000",
                    "runs": [
                        _run("signature", 16, 9600),
                        _run("paytree", 16, 9600, start_ms=2_000_000),
                    ],
                }
            )
        )

        # Avoid hitting Prometheus / Pyroscope / drawing heavy per-config charts.
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.generate_plots_from_intervals",
            lambda *a, **k: [],
        )
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.generate_aggregate_plots",
            lambda *a, **k: [str(tmp_path / "agg.png")],
        )
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.generate_profile_outputs",
            lambda *a, **k: [],
        )
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.export_raw_run_table",
            lambda *a, **k: None,
        )

        written = generate_sweep_plots(
            timing_path=str(timing),
            output_root=str(tmp_path / "plots"),
        )
        assert (tmp_path / "plots" / "20260722_120000").is_dir()
        assert written == [str(tmp_path / "agg.png")]
