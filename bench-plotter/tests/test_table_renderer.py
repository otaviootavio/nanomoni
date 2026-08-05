"""Tests for the shared table figure + CSV renderer."""

from __future__ import annotations

import csv
from pathlib import Path

from bench_plotter.plotting.table_renderer import create_stats_table, format_cell


class TestFormatCell:
    def test_missing_renders_as_placeholder(self) -> None:
        assert format_cell(None) == "-"

    def test_floats_use_three_significant_figures(self) -> None:
        assert format_cell(1.23456) == "1.23"
        assert format_cell(0.000123456) == "0.000123"

    def test_large_numbers_never_use_scientific_notation(self) -> None:
        # These cells are compared digit-for-digit against their neighbours, so
        # "1.74e+03" beside "938" would defeat the whole point of the column.
        assert format_cell(247296.0) == "247296"
        assert format_cell(1739.21) == "1739"

    def test_strings_pass_through(self) -> None:
        assert format_cell("signature") == "signature"


class TestCreateStatsTable:
    def test_writes_png_and_csv_with_raw_values(self, tmp_path: Path) -> None:
        out = tmp_path / "stats.png"
        create_stats_table(
            col_labels=["mode", "mean_ms", "stddev_ms"],
            rows=[["signature", 1.23456789, 0.5], ["payword", 2.0, None]],
            title="Latency",
            output_path=str(out),
        )

        assert out.exists()
        csv_path = out.with_suffix(".csv")
        rows = list(csv.DictReader(open(csv_path)))
        assert [r["mode"] for r in rows] == ["signature", "payword"]
        # The CSV keeps full precision; only the PNG rounds for display.
        assert rows[0]["mean_ms"] == "1.23456789"
        assert rows[1]["stddev_ms"] == ""

    def test_no_rows_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "stats.png"
        create_stats_table(col_labels=["mode"], rows=[], output_path=str(out))
        assert not out.exists()
        assert not out.with_suffix(".csv").exists()
