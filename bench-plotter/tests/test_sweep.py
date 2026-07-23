"""Unit tests for the TPS-sweep plotting helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from bench_plotter.draw_worker import DRAW_REGISTRY
from bench_plotter.plotting.common import PALETTE
from bench_plotter.plotting.sweep_renderers import create_sweep_line_plot
from bench_plotter.plotting.windowing import steady_state_samples
from bench_plotter.sweep.aggregate import _latency_series, _mode_style, _series_by_mode
from bench_plotter.sweep.runner import (
    config_dirname,
    group_runs_by_config,
    generate_sweep_plots,
)


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


class TestModeStyle:
    def test_known_modes_get_stable_palette_slots(self) -> None:
        paytree = _mode_style("paytree")
        payword = _mode_style("payword")
        signature = _mode_style("signature")
        assert paytree["color"] == PALETTE[0]
        assert payword["color"] == PALETTE[1]
        assert signature["color"] == PALETTE[2]
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
        assert by_label["signature"]["color"] == PALETTE[2]

    def test_latency_series_p50_only(self) -> None:
        scalars = [
            {"mode": "paytree", "tps": 16.0, "latency_p50": 0.5},
            {"mode": "paytree", "tps": 32.0, "latency_p50": 0.4},
            {"mode": "signature", "tps": 16.0, "latency_p50": 1.0},
        ]
        series = _latency_series(scalars)
        assert len(series) == 2
        by_label = {s["label"]: s for s in series}
        assert by_label["paytree"]["y_values"] == [0.5, 0.4]
        assert "y_low" not in by_label["paytree"]
        assert by_label["paytree"]["color"] == PALETTE[0]
        assert by_label["signature"]["color"] == PALETTE[2]


class TestGenerateSweepPlotsLoad:
    def test_object_shape_creates_timestamp_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        timing = tmp_path / "benchmark_timming.json"
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

        # Avoid hitting Prometheus / drawing heavy per-config charts.
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.generate_plots_from_intervals",
            lambda *a, **k: [],
        )
        monkeypatch.setattr(
            "bench_plotter.sweep.runner.generate_aggregate_plots",
            lambda *a, **k: [str(tmp_path / "agg.png")],
        )

        written = generate_sweep_plots(
            timing_path=str(timing),
            output_root=str(tmp_path / "plots"),
        )
        assert (tmp_path / "plots" / "20260722_120000").is_dir()
        assert written == [str(tmp_path / "agg.png")]
