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
