"""Tests for the ECDF renderers, focused on legend placement/handles.

``create_ecdf_plot`` draws through ``sns.ecdfplot(hue=...)``, which builds its
own ``ax.legend_`` directly rather than labeling axes artists -- a naive
``ax.legend()`` call afterward finds nothing and silently replaces it with an
empty legend (warns "No artists with labels found"). These tests guard
against that regression and check the multi-series legend renders in one row.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, List

from bench_plotter.plotting.distribution_renderers import (
    create_bucket_ecdf,
    create_ecdf_plot,
)


class TestCreateBucketEcdf:
    def test_writes_png_with_multi_series_legend_no_warnings(
        self, tmp_path: Path
    ) -> None:
        dists: List[Dict[str, Any]] = [
            {"label": "paytree", "edges": [1, 2, 4], "cum_fraction": [0.3, 0.6, 1.0]},
            {"label": "signature", "edges": [1, 2, 4], "cum_fraction": [0.5, 0.8, 1.0]},
        ]
        out = tmp_path / "ecdf.png"
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message="No artists with labels found")
            create_bucket_ecdf(dists, output_path=str(out))
        assert out.exists()
        assert out.stat().st_size > 0

    def test_no_data_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "ecdf.png"
        create_bucket_ecdf([], output_path=str(out))
        assert not out.exists()


class TestCreateEcdfPlot:
    def test_writes_png_with_seaborn_hue_legend_no_warnings(
        self, tmp_path: Path
    ) -> None:
        series_list: List[Dict[str, Any]] = [
            {"label": "paytree", "values": [10.0 + (i % 3) for i in range(20)]},
            {"label": "signature", "values": [12.0 + (i % 2) for i in range(20)]},
        ]
        out = tmp_path / "ecdf.png"
        # Escalates the seaborn-legend regression's specific UserWarning ("No
        # artists with labels found...") into a test failure instead of a
        # silently-empty legend; other warnings (e.g. matplotlib deprecations)
        # are left alone.
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message="No artists with labels found")
            create_ecdf_plot(series_list, output_path=str(out), trim=False)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_no_samples_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "ecdf.png"
        create_ecdf_plot([], output_path=str(out))
        assert not out.exists()
