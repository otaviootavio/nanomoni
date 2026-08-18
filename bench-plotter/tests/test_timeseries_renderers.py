"""Tests for the raw-timeseries overlay renderer (per-config resource charts).

``create_multi_line_plot`` draws unsmoothed series that can spike anywhere in
the plot, including right at the top -- an inside-axes top-left legend once
crowded a peak that reached the y-limit's headroom. The legend now lives
above the axes (wrapping at 3/row), with the title's pad reserving room for
it; these tests guard against both the original overlap and later pad
regressions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from bench_plotter.draw_worker import DRAW_REGISTRY
from bench_plotter.plotting.timeseries_renderers import create_multi_line_plot


def _series(label: str, values: List[float]) -> Dict[str, Any]:
    return {
        "label": label,
        "timestamps": list(range(len(values))),
        "values": values,
    }


class TestCreateMultiLinePlot:
    def test_line_multi_in_registry(self) -> None:
        assert "line_multi" in DRAW_REGISTRY

    def test_writes_png_with_five_series_legend_wraps(self, tmp_path: Path) -> None:
        # 5 modes is this chart family's real-world max (mode_style.KNOWN_MODES);
        # capped at ncol=3 so this wraps to 2 rows rather than forcing one wide row.
        series_list = [
            _series(mode, [10.0 * (idx + 1)] * 5)
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
        out = tmp_path / "multi_line.png"
        create_multi_line_plot(series_list, output_path=str(out))
        assert out.exists()
        assert out.stat().st_size > 0

    def test_empty_series_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.png"
        create_multi_line_plot([], output_path=str(out))
        assert not out.exists()

    def test_all_skipped_series_does_not_crash_legend(self, tmp_path: Path) -> None:
        # Every entry lacks timestamps/values, so drawn_count stays 0 -- ncol
        # must floor at 1, or matplotlib rejects legend(ncol=0).
        out = tmp_path / "skipped.png"
        create_multi_line_plot(
            [{"label": "signature", "timestamps": [], "values": []}],
            output_path=str(out),
        )
        assert out.exists()

    def test_linear_fit_overlay_writes_png(self, tmp_path: Path) -> None:
        # Two growing series (mimics the unbounded PayTree merkle-node leak):
        # show_linear_fit=True should overlay a y=mx+n line per series without
        # otherwise changing the write contract.
        series_list = [
            _series("paytree_first_opt", [10.0, 20.0, 30.0, 40.0, 50.0]),
            _series("paytree_child_pair", [5.0, 15.0, 25.0, 35.0, 45.0]),
        ]
        out = tmp_path / "linear_fit.png"
        create_multi_line_plot(series_list, output_path=str(out), show_linear_fit=True)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_linear_fit_skipped_below_two_points(self, tmp_path: Path) -> None:
        # A single-sample series has nothing to fit a line through; polyfit
        # must not be called (it would raise) and the plot should still write.
        out = tmp_path / "single_point.png"
        create_multi_line_plot(
            [_series("paytree_first_opt", [10.0])],
            output_path=str(out),
            show_linear_fit=True,
        )
        assert out.exists()

    def test_linear_fit_ignores_non_leaky_modes(self, tmp_path: Path) -> None:
        # signature/paytree/payword hold flat, so show_linear_fit=True must
        # not fit or annotate them -- only paytree_first_opt/child_pair.
        out = tmp_path / "non_leaky.png"
        create_multi_line_plot(
            [_series("signature", [10.0, 10.0, 10.0])],
            output_path=str(out),
            show_linear_fit=True,
        )
        assert out.exists()
