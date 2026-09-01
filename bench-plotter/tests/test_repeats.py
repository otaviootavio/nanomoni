"""Unit tests for reduce_repeats / reduce_repeat_timeseries."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from bench_plotter.repeats import reduce_repeat_timeseries, reduce_repeats


class TestReduceRepeats:
    def test_single_run_per_group_passes_through_with_zero_width_bounds(self) -> None:
        rows = [
            {
                "mode": "signature",
                "tps": 16.0,
                "total_requests": 1920.0,
                "crypto_ms_per_payment": 0.5,
            },
            {
                "mode": "paytree",
                "tps": 16.0,
                "total_requests": 1920.0,
                "crypto_ms_per_payment": 0.2,
            },
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 2
        by_mode = {r["mode"]: r for r in reduced}
        assert by_mode["signature"]["crypto_ms_per_payment"] == pytest.approx(0.5)
        assert by_mode["signature"]["crypto_ms_per_payment_low"] == pytest.approx(0.5)
        assert by_mode["signature"]["crypto_ms_per_payment_high"] == pytest.approx(0.5)
        assert by_mode["signature"]["crypto_ms_per_payment_n"] == 1

    def test_averages_repeats_and_adds_std_dev_bounds(self) -> None:
        rows = [
            {
                "mode": "signature",
                "tps": 16.0,
                "total_requests": 1920.0,
                "crypto_ms_per_payment": v,
            }
            for v in (1.0, 2.0, 3.0)
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 1
        row = reduced[0]
        # mean=2.0, sample std dev (ddof=1) = 1.0
        assert row["crypto_ms_per_payment"] == pytest.approx(2.0)
        assert row["crypto_ms_per_payment_low"] == pytest.approx(1.0)
        assert row["crypto_ms_per_payment_high"] == pytest.approx(3.0)
        assert row["crypto_ms_per_payment_n"] == 3

    def test_keeps_groups_separate_by_mode_and_tps(self) -> None:
        rows = [
            {"mode": "signature", "tps": 16.0, "total_requests": 1920.0, "v": 1.0},
            {"mode": "signature", "tps": 16.0, "total_requests": 1920.0, "v": 3.0},
            {"mode": "signature", "tps": 32.0, "total_requests": 3840.0, "v": 10.0},
            {"mode": "paytree", "tps": 16.0, "total_requests": 1920.0, "v": 5.0},
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 3
        by_key = {(r["mode"], r["tps"]): r for r in reduced}
        assert by_key[("signature", 16.0)]["v"] == pytest.approx(2.0)
        assert by_key[("signature", 16.0)]["v_n"] == 2
        assert by_key[("signature", 32.0)]["v"] == pytest.approx(10.0)
        assert by_key[("signature", 32.0)]["v_n"] == 1
        assert by_key[("paytree", 16.0)]["v"] == pytest.approx(5.0)

    def test_keeps_groups_separate_by_total_requests_too(self) -> None:
        # A duration sweep (same mode + target TPS, several RUN_DURATION_SEC
        # values) produces runs sharing (mode, tps) but not total_requests.
        # Those must NOT be treated as repeats of the same point -- doing so
        # would average away the very amortization trend such a sweep exists
        # to measure.
        rows = [
            {"mode": "signature", "tps": 16.0, "total_requests": 1920.0, "v": 1.0},
            {"mode": "signature", "tps": 16.0, "total_requests": 1920.0, "v": 3.0},
            {"mode": "signature", "tps": 16.0, "total_requests": 2560.0, "v": 100.0},
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 2
        by_key = {(r["mode"], r["tps"], r["total_requests"]): r for r in reduced}
        assert by_key[("signature", 16.0, 1920.0)]["v"] == pytest.approx(2.0)
        assert by_key[("signature", 16.0, 1920.0)]["v_n"] == 2
        assert by_key[("signature", 16.0, 2560.0)]["v"] == pytest.approx(100.0)
        assert by_key[("signature", 16.0, 2560.0)]["v_n"] == 1

    def test_drops_rows_missing_a_group_key(self) -> None:
        rows: List[Dict[str, Any]] = [
            {"mode": "signature", "tps": 16.0, "total_requests": 1920.0, "v": 1.0},
            {"mode": "signature", "total_requests": 1920.0, "v": 2.0},  # missing tps
            {"tps": 16.0, "total_requests": 1920.0, "v": 3.0},  # missing mode
            {"mode": "signature", "tps": 16.0, "v": 4.0},  # missing total_requests
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 1
        assert reduced[0]["mode"] == "signature"

    def test_non_numeric_fields_are_not_reduced(self) -> None:
        rows: List[Dict[str, Any]] = [
            {
                "mode": "signature",
                "tps": 16.0,
                "total_requests": 1920.0,
                "payload": {"a": 1},
                "v": 1.0,
            },
            {
                "mode": "signature",
                "tps": 16.0,
                "total_requests": 1920.0,
                "payload": {"a": 2},
                "v": 3.0,
            },
        ]
        reduced = reduce_repeats(rows)
        assert len(reduced) == 1
        # Comes from whichever row was first; not meant to be read after
        # reduction, but must not crash trying to "average" a dict.
        assert reduced[0]["payload"] == {"a": 1}
        assert reduced[0]["v"] == pytest.approx(2.0)

    def test_empty_input_returns_empty(self) -> None:
        assert reduce_repeats([]) == []


def _ts_run(
    mode: str,
    values: List[float],
    *,
    start: float = 1000.0,
    step: float = 1.0,
) -> Dict[str, Any]:
    return {
        "interval_mode": mode,
        "timestamps": [start + i * step for i in range(len(values))],
        "values": values,
    }


class TestReduceRepeatTimeseries:
    def test_single_run_per_mode_passes_through(self) -> None:
        runs = [
            _ts_run("signature", [1.0, 2.0, 3.0]),
            _ts_run("paytree", [4.0, 5.0]),
        ]
        reduced = reduce_repeat_timeseries(runs)
        assert len(reduced) == 2
        by_mode = {r["interval_mode"]: r for r in reduced}
        assert by_mode["signature"]["values"] == [1.0, 2.0, 3.0]
        assert "values_low" not in by_mode["signature"]
        assert by_mode["paytree"]["values"] == [4.0, 5.0]

    def test_averages_aligned_repeats_and_adds_std_band(self) -> None:
        # Three identical-length repeats of signature at the same elapsed grid.
        # At each point values are {1, 2, 3} -> mean=2, sample std=1.
        runs = [
            _ts_run("signature", [1.0, 1.0, 1.0], start=100.0),
            _ts_run("signature", [2.0, 2.0, 2.0], start=200.0),
            _ts_run("signature", [3.0, 3.0, 3.0], start=300.0),
        ]
        reduced = reduce_repeat_timeseries(runs)
        assert len(reduced) == 1
        row = reduced[0]
        assert row["interval_mode"] == "signature"
        assert row["values"] == pytest.approx([2.0, 2.0, 2.0])
        assert row["values_low"] == pytest.approx([1.0, 1.0, 1.0])
        assert row["values_high"] == pytest.approx([3.0, 3.0, 3.0])
        # Absolute timestamps are anchored on the first repeat's start.
        assert row["timestamps"][0] == pytest.approx(100.0)

    def test_clips_to_shortest_repeat_duration(self) -> None:
        # First repeat lasts 4s (5 samples at 1s); second lasts only 2s.
        # Merged grid must stop at elapsed=2.0 (three points: 0,1,2).
        runs = [
            _ts_run("signature", [10.0, 20.0, 30.0, 40.0, 50.0], start=0.0),
            _ts_run("signature", [12.0, 22.0, 32.0], start=100.0),
        ]
        reduced = reduce_repeat_timeseries(runs)
        assert len(reduced) == 1
        row = reduced[0]
        assert len(row["values"]) == 3
        assert row["timestamps"][-1] - row["timestamps"][0] == pytest.approx(2.0)
        assert row["values"] == pytest.approx([11.0, 21.0, 31.0])

    def test_keeps_modes_separate(self) -> None:
        runs = [
            _ts_run("signature", [1.0, 3.0]),
            _ts_run("signature", [5.0, 7.0]),
            _ts_run("paytree", [10.0, 10.0]),
        ]
        reduced = reduce_repeat_timeseries(runs)
        assert len(reduced) == 2
        by_mode = {r["interval_mode"]: r for r in reduced}
        assert by_mode["signature"]["values"] == pytest.approx([3.0, 5.0])
        assert "values_low" in by_mode["signature"]
        assert by_mode["paytree"]["values"] == [10.0, 10.0]
        assert "values_low" not in by_mode["paytree"]

    def test_drops_runs_missing_label(self) -> None:
        runs: List[Dict[str, Any]] = [
            _ts_run("signature", [1.0, 2.0]),
            {"timestamps": [0.0, 1.0], "values": [9.0, 9.0]},  # no interval_mode
        ]
        reduced = reduce_repeat_timeseries(runs)
        assert len(reduced) == 1
        assert reduced[0]["interval_mode"] == "signature"

    def test_empty_input_returns_empty(self) -> None:
        assert reduce_repeat_timeseries([]) == []
