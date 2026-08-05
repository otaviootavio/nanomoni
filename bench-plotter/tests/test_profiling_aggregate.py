"""Unit tests for the per-run Pyroscope profile extraction (profiling/aggregate.py)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from bench_plotter.profiling.aggregate import (
    _extract_record,
    _fetch_run_profile,
    _highlight_for_mode,
    build_profile_draw_tasks,
)
from bench_plotter.plotting.profile_bar_renderer import (
    _CRYPTO_COLOR,
    _DB_READ_COLOR,
    _DB_WRITE_COLOR,
    _SERIALIZE_COLOR,
)

# A signature-mode request: the endpoint calls crypto, a repository read that
# issues one mget, and a repository write that serializes then runs a script.
# The nested mget mimics redis-py's same-named method inside our store's.
_NAMES = [
    "total",
    "run_endpoint_function",
    "receive_payment",
    "idle",
    "verify_signature_bytes",
    "get_by_channel_id",
    "save_payment",
    "mget",
    "model_dump_json",
    "run_script",
]
_LEVELS = [
    [0, 100, 0, 0],
    [0, 100, 0, 1],
    [0, 80, 40, 2, 0, 20, 20, 3],
    # verify(10) + get_by_channel_id(15) + save_payment(15)
    [0, 10, 10, 4, 0, 15, 3, 5, 0, 15, 2, 6],
    # mget(12) under get_by_channel_id; model_dump_json(3) + run_script(10)
    # under save_payment
    [10, 12, 4, 7, 3, 3, 3, 8, 0, 10, 10, 9],
    # redis-py's own mget(8) nested inside our store's mget
    [10, 8, 8, 7],
]


def _payload(sample_rate: float = 10.0) -> Dict[str, Any]:
    return {
        "flamebearer": {
            "names": list(_NAMES),
            "levels": [list(lvl) for lvl in _LEVELS],
        },
        "metadata": {"sampleRate": sample_rate},
    }


def _counter_payload(values: Optional[List[float]]) -> Dict[str, Any]:
    """A Prometheus query_range payload for a single series.

    ``values`` is the raw counter reading at each of a few evenly spaced
    timestamps -- callers only care about the first-vs-last delta.
    ``None`` mimics "no data returned" (e.g. an unrecognized mode/metric).
    """
    if values is None:
        return {"data": {"result": []}}
    return {
        "data": {
            "result": [
                {
                    "metric": {"__name__": "payment_requests_total"},
                    "values": [[1000.0 + i, str(v)] for i, v in enumerate(values)],
                }
            ]
        }
    }


def _run(
    mode: str = "signature",
    tps: float = 200.0,
    start_ms: int = 1_000_000,
    finish_ms: int = 1_100_000,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "tps": tps,
        "total_requests": 12000,
        "prometheus_timestamps": {"start_ms": start_ms, "finish_ms": finish_ms},
    }


class TestExtractRecord:
    def test_computes_macro_micro_split(self) -> None:
        # sampleRate=10: ticks/10 = seconds. crypto=10, db read=mget(12) with
        # the nested mget(8) counted once, db write=run_script(10), serialize=3,
        # other = 80 - 10 - 12 - 10 - 3 = 45. The repository frames themselves
        # (get_by_channel_id, save_payment) are not a bucket of their own, so
        # their non-I/O, non-marshalling time falls into other.
        record = _extract_record(_payload(), "signature", 200.0)
        assert record["total_time_s"] == pytest.approx(10.0)
        assert record["run_endpoint_time_s"] == pytest.approx(10.0)
        assert record["macro_time_s"] == pytest.approx(8.0)
        assert record["crypto_time_s"] == pytest.approx(1.0)
        assert record["db_read_time_s"] == pytest.approx(1.2)
        assert record["db_write_time_s"] == pytest.approx(1.0)
        assert record["serialize_time_s"] == pytest.approx(0.3)
        assert record["other_time_s"] == pytest.approx(4.5)

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(KeyError):
            _extract_record(_payload(), "not_a_real_mode", 200.0)


class TestHighlightForMode:
    def test_maps_crypto_db_and_serialize_functions_to_shared_colors(self) -> None:
        highlight = _highlight_for_mode("signature")
        assert highlight["verify_signature_bytes"] == _CRYPTO_COLOR
        assert highlight["mget"] == _DB_READ_COLOR
        assert highlight["run_script"] == _DB_WRITE_COLOR
        assert highlight["model_dump_json"] == _SERIALIZE_COLOR


async def _call(run: Dict[str, Any]) -> Any:
    # A Semaphore constructed outside a running loop binds to whatever loop
    # asyncio.get_event_loop() resolves to on Python 3.9, which can be a
    # stale/closed one left by an earlier test's asyncio.run(); creating it
    # inside the coroutine that asyncio.run() drives avoids that entirely.
    sem = asyncio.Semaphore(1)
    return await _fetch_run_profile(run, sem)


_QUERY_RANGE = "bench_plotter.profiling.aggregate.query_range"
_RENDER = "bench_plotter.profiling.aggregate.pyroscope_fetch.render"


class TestFetchRunProfile:
    def test_missing_mode_or_tps_returns_none(self) -> None:
        run = _run()
        del run["mode"]
        assert asyncio.run(_call(run)) is None

    def test_mode_not_in_taxonomy_returns_none(self) -> None:
        assert asyncio.run(_call(_run(mode="unknown"))) is None

    def test_missing_window_returns_none(self) -> None:
        run = _run()
        run["prometheus_timestamps"] = {}
        assert asyncio.run(_call(run)) is None

    @patch(_QUERY_RANGE, new_callable=AsyncMock)
    @patch(_RENDER, new_callable=AsyncMock)
    def test_successful_fetch_builds_record(
        self, mock_render: AsyncMock, mock_query_range: AsyncMock
    ) -> None:
        mock_render.return_value = _payload()
        mock_query_range.return_value = _counter_payload([0.0, 9000.0])
        record = asyncio.run(_call(_run()))
        assert record is not None
        assert record["mode"] == "signature"
        assert record["tps"] == 200.0
        assert record["total_requests"] == 12000
        assert record["macro_time_s"] == pytest.approx(8.0)

        # The run's whole window is queried, untrimmed: the harness's pre-run
        # sleep and post-run drain already leave idle margins inside it, and
        # starting later would truncate the payment counter's delta.
        _, kwargs = mock_render.call_args
        assert kwargs["start_unix"] == pytest.approx(1000.0)
        assert kwargs["end_unix"] == pytest.approx(1100.0)

        # The payment count comes from the vendor's own counter over exactly
        # that same window, not a TPS/total_requests model.
        _, qkwargs = mock_query_range.call_args
        assert qkwargs["start_unix"] == pytest.approx(1000.0)
        assert qkwargs["end_unix"] == pytest.approx(1100.0)
        assert "payment_requests_total" in mock_query_range.call_args.kwargs["query"]

    @patch(_RENDER, new_callable=AsyncMock)
    def test_query_failure_returns_none(self, mock_render: AsyncMock) -> None:
        mock_render.side_effect = ValueError("pyroscope down")
        assert asyncio.run(_call(_run())) is None

    @patch(_QUERY_RANGE, new_callable=AsyncMock)
    @patch(_RENDER, new_callable=AsyncMock)
    def test_prometheus_failure_propagates(
        self, mock_render: AsyncMock, mock_query_range: AsyncMock
    ) -> None:
        # Unlike a down Pyroscope, a down Prometheus must not be swallowed
        # into a None/skipped-run result: every per-payment number this stage
        # produces depends on the payment count it would have supplied, so a
        # wrong (modeled) number is worse than surfacing the failure.
        mock_render.return_value = _payload()
        mock_query_range.side_effect = ValueError("prometheus unreachable")
        with pytest.raises(ValueError, match="prometheus unreachable"):
            asyncio.run(_call(_run()))

    @patch(_QUERY_RANGE, new_callable=AsyncMock)
    @patch(_RENDER, new_callable=AsyncMock)
    def test_per_payment_fields_use_the_vendor_counter_delta(
        self, mock_render: AsyncMock, mock_query_range: AsyncMock
    ) -> None:
        mock_render.return_value = _payload()
        mock_query_range.return_value = _counter_payload([100.0, 9100.0])
        record = asyncio.run(_call(_run()))
        assert record is not None
        assert record["profile_payments"] == pytest.approx(9000.0)
        assert record["crypto_ms_per_payment"] == pytest.approx(1.0 / 9000 * 1000)
        assert record["db_read_ms_per_payment"] == pytest.approx(1.2 / 9000 * 1000)
        assert record["db_write_ms_per_payment"] == pytest.approx(1.0 / 9000 * 1000)
        assert record["serialize_ms_per_payment"] == pytest.approx(0.3 / 9000 * 1000)
        assert record["other_ms_per_payment"] == pytest.approx(4.5 / 9000 * 1000)

    @patch(_QUERY_RANGE, new_callable=AsyncMock)
    @patch(_RENDER, new_callable=AsyncMock)
    def test_per_payment_is_none_when_counter_has_no_data(
        self, mock_render: AsyncMock, mock_query_range: AsyncMock
    ) -> None:
        mock_render.return_value = _payload()
        mock_query_range.return_value = _counter_payload(None)
        record = asyncio.run(_call(_run()))
        assert record is not None
        assert record["profile_payments"] is None
        assert record["crypto_ms_per_payment"] is None


class TestBuildProfileDrawTasks:
    @patch(_QUERY_RANGE, new_callable=AsyncMock)
    @patch(_RENDER, new_callable=AsyncMock)
    def test_task_shape_for_two_tps_levels(
        self,
        mock_render: AsyncMock,
        mock_query_range: AsyncMock,
        tmp_path: Any,
    ) -> None:
        mock_render.return_value = _payload()
        mock_query_range.return_value = _counter_payload([0.0, 9000.0])
        runs = [
            _run(mode="signature", tps=200.0),
            _run(mode="signature", tps=300.0),
        ]
        tasks = build_profile_draw_tasks(runs, str(tmp_path))
        by_fn: Dict[str, list] = {}
        for t in tasks:
            by_fn.setdefault(t.fn_name, []).append(t)

        # One flame graph per run, each cropped to the mode's own endpoint
        # (receive_payment for signature), not the generic FastAPI wrapper.
        assert len(by_fn["flame_graph"]) == 2
        for t in by_fn["flame_graph"]:
            assert t.kwargs["focus"] == "receive_payment"

        # One bar chart PER TPS, written inside that TPS's own profile folder
        # alongside that config's flame graphs.
        assert len(by_fn["profile_macro_micro_bar"]) == 2
        bar_paths = {t.output_path for t in by_fn["profile_macro_micro_bar"]}
        for tps in (200, 300):
            assert (
                str(
                    tmp_path
                    / f"tps{tps}_req12000"
                    / "profile"
                    / "profile_macro_micro.png"
                )
                in bar_paths
            )

        # One combined table (CSV + PNG).
        assert len(by_fn["profile_macro_micro_table"]) == 1

        # Absolute and per-payment vs-TPS line charts, per micro category.
        categories = ("crypto", "db_read", "db_write", "serialize", "other")
        assert len(by_fn["sweep_line"]) == 2 * len(categories)
        line_paths = {t.output_path for t in by_fn["sweep_line"]}
        for category in categories:
            assert str(tmp_path / f"{category}_time_vs_tps.png") in line_paths
            assert str(tmp_path / f"{category}_time_per_payment_vs_tps.png") in (
                line_paths
            )
