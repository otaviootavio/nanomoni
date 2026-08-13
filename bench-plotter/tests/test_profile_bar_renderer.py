"""Tests for the per-TPS macro/micro bar chart and the combined table PNG+CSV."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from bench_plotter.plotting.profile_bar_renderer import (
    create_macro_micro_bar,
    create_macro_micro_table,
)


def _record(mode: str, tps: float, **overrides: float) -> Dict[str, Any]:
    base = {
        "mode": mode,
        "tps": tps,
        "total_time_s": 10.0,
        "run_endpoint_time_s": 9.0,
        "macro_time_s": 8.0,
        "crypto_time_s": 2.0,
        "db_read_time_s": 1.2,
        "db_write_time_s": 0.8,
        "other_time_s": 3.0,
        "profile_payments": 8000.0,
        "crypto_ms_per_payment": 0.25,
        "db_read_ms_per_payment": 0.15,
        "db_write_ms_per_payment": 0.1,
        "other_ms_per_payment": 0.375,
    }
    base.update(overrides)
    return base


class TestCreateMacroMicroBar:
    def test_writes_one_png_per_call_no_csv(self, tmp_path: Path) -> None:
        records: List[Dict[str, Any]] = [
            _record("signature", 200.0),
            _record("paytree", 200.0),
        ]
        out = tmp_path / "profile_macro_micro_tps200.png"
        create_macro_micro_bar(records, output_path=str(out))

        assert out.exists()
        assert not out.with_suffix(".csv").exists()

    def test_no_records_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "profile_macro_micro_tps200.png"
        create_macro_micro_bar([], output_path=str(out))
        assert not out.exists()

    def test_records_without_a_payment_count_are_skipped(self, tmp_path: Path) -> None:
        # Bars are per payment, so a run whose payment count couldn't be read
        # has nothing to normalize by and cannot be drawn.
        record = _record("signature", 200.0)
        record.update(
            profile_payments=None,
            crypto_ms_per_payment=None,
            db_read_ms_per_payment=None,
            db_write_ms_per_payment=None,
            other_ms_per_payment=None,
        )
        out = tmp_path / "profile_macro_micro_tps200.png"
        create_macro_micro_bar([record], output_path=str(out))
        assert not out.exists()


class TestCreateMacroMicroTable:
    def test_writes_png_and_csv(self, tmp_path: Path) -> None:
        records: List[Dict[str, Any]] = [
            _record("signature", 200.0),
            _record("paytree", 200.0),
            _record("signature", 300.0),
            _record("paytree", 300.0),
        ]
        out = tmp_path / "profile_macro_micro_table.png"
        create_macro_micro_table(records, output_path=str(out))

        assert out.exists()
        csv_path = out.with_suffix(".csv")
        assert csv_path.exists()

        rows = list(csv.DictReader(open(csv_path)))
        assert len(rows) == 4
        by_key = {(r["mode"], r["tps"]): r for r in rows}
        row = by_key[("signature", "200.0")]
        assert float(row["macro_time_s"]) == 8.0
        assert float(row["crypto_time_s"]) == 2.0
        assert float(row["db_read_time_s"]) == 1.2
        assert float(row["db_write_time_s"]) == 0.8

    def test_no_records_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "profile_macro_micro_table.png"
        create_macro_micro_table([], output_path=str(out))
        assert not out.exists()
        assert not out.with_suffix(".csv").exists()
