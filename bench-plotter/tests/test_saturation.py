"""Unit tests for the expected-vs-real TPS (saturation) analysis."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from bench_plotter.draw_worker import DRAW_REGISTRY
from bench_plotter.io_utils import load_timing_file, load_virtual_clients
from bench_plotter.plotting import sweep_renderers
from bench_plotter.plotting.sweep_renderers import (
    create_delta_table,
    create_identity_comparison_plot,
)
from bench_plotter.saturation.aggregate import (
    MET_TARGET_RATIO,
    achieved_tps_expr,
    build_delta_table,
    build_series,
    ideal_traffic_span_seconds,
    plateau_samples,
    rate_window_too_short,
    saturation_tps,
    summarize,
    sustained_rate,
)
from bench_plotter.saturation import runner
from bench_plotter.saturation.runner import _client_config_label


def _point(
    mode: str,
    expected: float,
    achieved: Optional[float],
) -> Dict[str, Any]:
    ratio = None if achieved is None else achieved / expected
    return {
        "mode": mode,
        "expected_tps": expected,
        "achieved_tps": achieved,
        "ratio": ratio,
        "met_target": ratio is not None and ratio >= MET_TARGET_RATIO,
        "status": "success",
    }


class TestAchievedTpsExpr:
    def test_uses_the_modes_own_counter(self) -> None:
        expr = achieved_tps_expr("paytree_child_pair")
        assert expr is not None
        assert "paytree_child_pair_payment_requests_total" in expr
        assert 'status="success"' in expr
        assert "[10s]" in expr

    def test_signature_uses_bare_counter_name(self) -> None:
        expr = achieved_tps_expr("signature")
        assert expr is not None
        assert expr.startswith("rate(payment_requests_total{")

    def test_unknown_mode_has_no_query(self) -> None:
        assert achieved_tps_expr("not_a_mode") is None


def _samples(values: List[float], step: float = 5.0) -> List[Any]:
    """Attach evenly spaced timestamps, as a 5s-step range query returns."""
    return [(i * step, v) for i, v in enumerate(values)]


class TestPlateauSamples:
    def test_drops_ramp_and_drain_partial_windows(self) -> None:
        # The exact shape a 16 TPS run produces: two ramp samples, a flat plateau,
        # one drain sample. Only the plateau is fully covered by the rate window.
        values = [0.0, 5.0, 13.9, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 11.0]
        assert plateau_samples(_samples(values), window_seconds=10.0) == [16.0] * 6

    def test_a_ramp_sample_near_the_plateau_is_still_dropped(self) -> None:
        # 13.9 is only 13% under the plateau, so no magnitude band can exclude it
        # without also excluding a real 13% shortfall. Time coverage can.
        values = [0.0, 5.0, 13.9, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 11.0]
        assert 13.9 not in plateau_samples(_samples(values), window_seconds=10.0)

    def test_keeps_genuine_mid_run_variation(self) -> None:
        # A dip inside the covered region is real (vendor stall, or the client
        # progressively falling behind) and must survive.
        values = [0.0, 100.0, 500.0, 508.0, 508.0, 300.0, 508.0, 508.0, 250.0, 0.0]
        kept = plateau_samples(_samples(values), window_seconds=10.0)
        assert 300.0 in kept

    def test_falls_back_when_nothing_is_fully_covered(self) -> None:
        # Traffic shorter than 2x the window leaves no covered sample; report the
        # active ones rather than nothing (rate_window_too_short flags this run).
        values = [0.0, 200.0, 210.0, 0.0]
        assert plateau_samples(_samples(values), window_seconds=10.0) == [200.0, 210.0]

    def test_no_traffic(self) -> None:
        assert plateau_samples(_samples([0.0, 0.0, 0.0])) == []
        assert plateau_samples([]) == []


class TestSustainedRate:
    def test_reports_the_plateau_exactly(self) -> None:
        # Previously this averaged the 13.9 ramp sample in and reported 15.74 for a
        # client that was pacing at exactly 16.0.
        values = [0.0, 5.0, 13.9, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 11.0]
        assert sustained_rate(_samples(values)) == pytest.approx(16.0)

    def test_ignores_setup_and_drain_zeros(self) -> None:
        # A PayTree run sends nothing while the tree is built, then drains to 0.
        values = [0.0, 0.0, 0.0, 250.0, 500.0, 500.0, 500.0, 500.0, 500.0, 200.0, 0.0]
        rate = sustained_rate(_samples(values))
        assert rate == pytest.approx(500.0)

    def test_short_run_falls_back_to_active_samples(self) -> None:
        assert sustained_rate(_samples([0.0, 200.0, 210.0])) == pytest.approx(205.0)

    def test_no_traffic_yields_none(self) -> None:
        assert sustained_rate(_samples([0.0, 0.0, 0.0])) is None
        assert sustained_rate([]) is None


class TestRateWindowGuard:
    def test_span_is_count_over_target(self) -> None:
        assert ideal_traffic_span_seconds(2880, 64) == pytest.approx(45.0)
        assert ideal_traffic_span_seconds(122880, 1024) == pytest.approx(120.0)

    def test_span_unknown_without_a_count(self) -> None:
        assert ideal_traffic_span_seconds(None, 64) is None
        assert ideal_traffic_span_seconds(0, 64) is None

    def test_burst_shorter_than_two_rate_windows_is_unmeasurable(self) -> None:
        # Traffic shorter than the window reads low by (span / window) no matter
        # what the client did -- the trap that produced a bogus SHORT verdict.
        assert rate_window_too_short(10.0) is True
        assert rate_window_too_short(19.0) is True

    def test_long_enough_run_is_measurable(self) -> None:
        # The sweep's 45s default sits comfortably above the 20s floor.
        assert rate_window_too_short(20.0) is False
        assert rate_window_too_short(45.0) is False

    def test_unknown_span_is_not_flagged(self) -> None:
        assert rate_window_too_short(None) is False


class TestSaturationTps:
    def test_last_on_target_before_shortfall(self) -> None:
        points = [
            _point("signature", 16, 16.0),
            _point("signature", 32, 32.0),
            _point("signature", 64, 63.5),
            _point("signature", 128, 70.0),
        ]
        assert saturation_tps(points, "signature") == 64

    def test_stops_at_first_shortfall(self) -> None:
        # 1024 lands inside tolerance by luck; the ceiling must not jump past the
        # 256 target the client already failed.
        points = [
            _point("signature", 128, 128.0),
            _point("signature", 256, 150.0),
            _point("signature", 1024, 1024.0),
        ]
        assert saturation_tps(points, "signature") == 128

    def test_none_when_even_the_lowest_target_falls_short(self) -> None:
        points = [_point("signature", 16, 4.0)]
        assert saturation_tps(points, "signature") is None

    def test_scoped_per_mode(self) -> None:
        points = [
            _point("signature", 64, 64.0),
            _point("paytree_child_pair", 64, 20.0),
        ]
        assert saturation_tps(points, "signature") == 64
        assert saturation_tps(points, "paytree_child_pair") is None


class TestBuildSeries:
    def test_one_line_per_mode_and_no_reference_line(self) -> None:
        points = [
            _point("signature", 16, 16.0),
            _point("signature", 32, 30.0),
            _point("payword", 16, 15.0),
            _point("payword", 32, 20.0),
        ]
        series = build_series(points)
        # The y = x line belongs to the renderer, which knows the axis range it
        # must span; only measured series come from here.
        assert [s["label"] for s in series] == ["payword (real)", "signature (real)"]
        assert series[1]["x_values"] == [16, 32]
        assert series[1]["y_values"] == [16.0, 30.0]

    def test_modes_get_distinct_colors(self) -> None:
        points = [_point("signature", 16, 16.0), _point("payword", 16, 15.0)]
        colors = {s["color"] for s in build_series(points)}
        assert len(colors) == 2

    def test_drops_points_without_data(self) -> None:
        points = [_point("signature", 16, 16.0), _point("signature", 32, None)]
        series = build_series(points)
        assert series[0]["x_values"] == [16]

    def test_empty_when_nothing_drawable(self) -> None:
        assert build_series([_point("signature", 16, None)]) == []


class TestBuildDeltaTable:
    def test_rows_are_targets_and_columns_are_protocols(self) -> None:
        points = [
            _point("signature", 16, 16.0),
            _point("signature", 32, 30.0),
            _point("payword", 16, 12.0),
            _point("payword", 32, 20.0),
        ]
        table = build_delta_table(points)
        assert table["tps_values"] == [16, 32]
        assert table["modes"] == ["payword", "signature"]
        # achieved[row][col] == real TPS for tps_values[row] and modes[col]
        assert table["achieved"] == [
            [pytest.approx(12.0), pytest.approx(16.0)],
            [pytest.approx(20.0), pytest.approx(30.0)],
        ]

    def test_missing_measurement_is_none_not_zero(self) -> None:
        # A None cell must stay distinguishable from a genuine achieved value of 0.
        points = [_point("signature", 16, None), _point("signature", 32, 32.0)]
        achieved = build_delta_table(points)["achieved"]
        assert achieved[0][0] is None
        assert achieved[1][0] == pytest.approx(32.0)

    def test_absent_mode_tps_combination_is_none(self) -> None:
        # payword was only swept at 16, signature only at 32.
        points = [_point("payword", 16, 15.0), _point("signature", 32, 30.0)]
        table = build_delta_table(points)
        assert table["modes"] == ["payword", "signature"]
        assert table["achieved"] == [
            [pytest.approx(15.0), None],
            [None, pytest.approx(30.0)],
        ]

    def test_empty_points(self) -> None:
        table = build_delta_table([])
        assert table == {"tps_values": [], "modes": [], "achieved": []}


class TestDeltaTableRenderer:
    def test_in_registry(self) -> None:
        assert "delta_table" in DRAW_REGISTRY

    def test_writes_png_and_csv(self, tmp_path: Path) -> None:
        out = tmp_path / "delta.png"
        create_delta_table(
            tps_values=[16, 32],
            modes=["signature", "payword"],
            achieved=[[16.0, 12.0], [30.0, None]],
            output_path=str(out),
        )
        csv_path = out.with_suffix(".csv")
        assert out.exists() and out.stat().st_size > 0
        assert csv_path.exists()

        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == ["Target TPS", "signature", "payword"]
        assert rows[1] == ["16", "16.0 (100.0%)", "12.0 (75.0%)"]
        # Missing cell renders as a placeholder, never as a number.
        assert rows[2] == ["32", "30.0 (93.8%)", "-"]

    def test_overshoot_is_above_100_percent(self, tmp_path: Path) -> None:
        out = tmp_path / "delta.png"
        create_delta_table(
            tps_values=[100],
            modes=["signature"],
            achieved=[[102.5]],
            output_path=str(out),
        )
        rows = list(csv.reader(out.with_suffix(".csv").open()))
        assert rows[1] == ["100", "102.5 (102.5%)"]

    def test_no_output_without_data(self, tmp_path: Path) -> None:
        out = tmp_path / "delta.png"
        create_delta_table(tps_values=[], modes=[], achieved=[], output_path=str(out))
        assert not out.exists()


class TestIdentityComparisonRenderer:
    def test_in_registry(self) -> None:
        assert "identity_comparison" in DRAW_REGISTRY

    def test_writes_png(self, tmp_path: Path) -> None:
        out = tmp_path / "identity.png"
        create_identity_comparison_plot(
            series_list=[
                {
                    "label": "signature (real)",
                    "x_values": [16, 32, 64, 128],
                    "y_values": [16.0, 32.0, 63.0, 70.0],
                }
            ],
            output_path=str(out),
        )
        assert out.exists() and out.stat().st_size > 0

    def test_axes_share_scale_limits_and_ticks(self, tmp_path: Path) -> None:
        # The whole point of the chart: y = x must render as a true diagonal, so
        # both axes need one scale, one range, and one set of ticks.
        captured: Dict[str, Any] = {}
        real_save = sweep_renderers.save_figure

        def _capture(fig: Any, output_path: str, **kwargs: Any) -> None:
            ax = fig.axes[0]
            captured["xscale"] = ax.get_xscale()
            captured["yscale"] = ax.get_yscale()
            captured["xlim"] = ax.get_xlim()
            captured["ylim"] = ax.get_ylim()
            captured["xticks"] = list(ax.get_xticks())
            captured["yticks"] = list(ax.get_yticks())
            captured["aspect"] = ax.get_aspect()
            real_save(fig, output_path, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sweep_renderers, "save_figure", _capture)
            create_identity_comparison_plot(
                series_list=[
                    {
                        "label": "signature (real)",
                        "x_values": [16, 32, 64],
                        "y_values": [16.0, 30.0, 40.0],
                    }
                ],
                output_path=str(tmp_path / "identity.png"),
            )

        assert captured["xscale"] == captured["yscale"] == "log"
        assert captured["xlim"] == captured["ylim"]
        assert captured["xticks"] == captured["yticks"]
        assert captured["aspect"] == 1.0

    def test_skips_non_positive_points(self, tmp_path: Path) -> None:
        # Log axes cannot represent 0; such a point is dropped, not clipped.
        out = tmp_path / "identity.png"
        create_identity_comparison_plot(
            series_list=[
                {"label": "signature", "x_values": [16, 32], "y_values": [0.0, 30.0]}
            ],
            output_path=str(out),
        )
        assert out.exists()

    def test_no_output_without_drawable_series(self, tmp_path: Path) -> None:
        out = tmp_path / "identity.png"
        create_identity_comparison_plot(series_list=[], output_path=str(out))
        assert not out.exists()

        create_identity_comparison_plot(
            series_list=[{"label": "s", "x_values": [16], "y_values": [0.0]}],
            output_path=str(out),
        )
        assert not out.exists()


class TestSummarize:
    def test_reports_ceiling_per_mode(self) -> None:
        points = [
            _point("signature", 16, 16.0),
            _point("signature", 32, 20.0),
        ]
        summary = summarize(points)
        assert summary["saturation_tps_by_mode"] == {"signature": 16}
        assert summary["met_target_ratio"] == MET_TARGET_RATIO
        assert summary["rate_window"] == "10s"
        assert summary["points"] == points


class TestLoadTimingFile:
    def test_reads_sweep_object_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        runs: List[Dict[str, Any]] = [{"mode": "signature", "tps": 16}]
        path.write_text(
            json.dumps({"server_run_timestamp": "20260730_120000", "runs": runs})
        )
        ts, loaded = load_timing_file(str(path))
        assert ts == "20260730_120000"
        assert loaded == runs

    def test_reads_legacy_bare_list(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        path.write_text(json.dumps([{"mode": "signature", "tps": 16}]))
        ts, loaded = load_timing_file(str(path))
        assert ts  # derived from now()
        assert len(loaded) == 1

    def test_tolerates_unexpected_shapes(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        path.write_text(json.dumps({"runs": "not-a-list"}))
        _ts, loaded = load_timing_file(str(path))
        assert loaded == []


class TestLoadVirtualClients:
    def test_reads_virtual_clients_field(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        path.write_text(json.dumps({"runs": [], "virtual_clients": 8}))
        assert load_virtual_clients(str(path)) == 8

    def test_none_when_field_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        path.write_text(json.dumps({"runs": []}))
        assert load_virtual_clients(str(path)) is None

    def test_none_for_legacy_bare_list(self, tmp_path: Path) -> None:
        path = tmp_path / "timing.json"
        path.write_text(json.dumps([{"mode": "signature", "tps": 16}]))
        assert load_virtual_clients(str(path)) is None


class TestSaturationReportProfiling:
    def test_profiles_through_the_same_stage_as_the_full_sweep(
        self, tmp_path: Path
    ) -> None:
        timing = tmp_path / "timing.json"
        timing.write_text(
            json.dumps(
                {
                    "server_run_timestamp": "20260801_120000",
                    "virtual_clients": 48,
                    "runs": [
                        {"mode": "signature", "tps": 4096, "status": "success"},
                        {"mode": "payword", "status": "success"},
                    ],
                }
            )
        )
        seen: Dict[str, Any] = {}

        def _profile(
            runs: List[Dict[str, Any]], output_dir: str, **_kwargs: Any
        ) -> List[str]:
            seen["runs"] = runs
            seen["output_dir"] = output_dir
            return [str(Path(output_dir) / "flame_signature.png")]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                runner,
                "collect_points",
                lambda _runs: [_point("signature", 4096, 4000.0)],
            )
            mp.setattr(runner, "generate_profile_outputs", _profile)
            written, _summary = runner.generate_saturation_report(
                timing_path=str(timing),
                output_root=str(tmp_path / "plots"),
            )

        out_dir = tmp_path / "plots" / "20260801_120000"
        # A run without tps has no place on the sweep's axis, so it is not profiled.
        assert [run["mode"] for run in seen["runs"]] == ["signature"]
        assert seen["output_dir"] == str(out_dir)
        assert str(out_dir / "flame_signature.png") in written


class TestClientConfigLabel:
    def test_singular_for_one_client(self) -> None:
        assert _client_config_label(1) == "single sequential client"

    def test_plural_for_many_clients(self) -> None:
        assert _client_config_label(8) == "8 virtual clients, each sequential"

    def test_unknown_when_absent(self) -> None:
        assert _client_config_label(None) == "sequential client(s), count unknown"
