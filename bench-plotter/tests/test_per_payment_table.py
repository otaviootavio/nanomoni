"""Tests for the client-egress-per-payment table transform."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from bench_plotter.pipeline.model import PlotJob, QuerySpec, ResultCache
from bench_plotter.pipeline.per_payment_table_transform import (
    transform_per_payment_table,
)


def _payload(values: List[float]) -> Dict[str, Any]:
    return {
        "data": {
            "result": [
                {
                    "metric": {"__name__": "m"},
                    "values": [[float(i) * 15, str(v)] for i, v in enumerate(values)],
                }
            ]
        }
    }


def _job(spec: QuerySpec, tps_by_mode: Dict[str, float]) -> PlotJob:
    return PlotJob(
        kind="per_payment_table",
        title="Client egress per payment",
        output_path="plots/client_resources/out_per_payment.png",
        section="client_resources",
        specs=[spec],
        params={
            "series": [{"spec": spec, "label": "payword"}],
            "tps_by_mode": tps_by_mode,
        },
    )


class TestTransformPerPaymentTable:
    def test_divides_egress_rate_by_the_payment_rate(self) -> None:
        # A flat 512 KiB/s plateau at 256 payments/s is 2 KiB (2048 bytes) of
        # request on the wire per payment.
        spec = QuerySpec("client_egress", 0.0, 100.0)
        cache: ResultCache = {spec: _payload([512.0] * 8)}

        tasks = transform_per_payment_table(_job(spec, {"payword": 256.0}), cache)

        assert len(tasks) == 1
        assert tasks[0].fn_name == "stats_table"
        (row,) = tasks[0].kwargs["rows"]
        mode, tps, kib_s, kib_per_payment, bytes_per_payment = row
        assert mode == "payword"
        assert tps == pytest.approx(256.0)
        assert kib_s == pytest.approx(512.0)
        assert kib_per_payment == pytest.approx(2.0)
        assert bytes_per_payment == pytest.approx(2048.0)

    def test_mode_without_a_known_tps_is_skipped(self) -> None:
        spec = QuerySpec("client_egress", 0.0, 100.0)
        cache: ResultCache = {spec: _payload([512.0] * 8)}
        assert transform_per_payment_table(_job(spec, {}), cache) == []

    def test_missing_payload_yields_no_task(self) -> None:
        spec = QuerySpec("client_egress", 0.0, 100.0)
        assert transform_per_payment_table(_job(spec, {"payword": 256.0}), {}) == []
