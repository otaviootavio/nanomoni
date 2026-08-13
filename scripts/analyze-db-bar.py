"""Check for a run-order confound: signature always runs first in each TPS
iteration (run_benchmark.sh calls run_signature, then paytree, then
paytree_first_opt, then paytree_child_pair, then payword, every iteration).
If the vendor container's CPU has any "cold start" ramp after an idle period
(CPU frequency scaling, scheduler/cache warmth), it would always land on
signature and never on the other four modes -- a bias unrelated to anything
algorithmic. This prints vendor container CPU utilization across one full
mode sequence to look for that ramp pattern at each run's boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

PROM = "http://localhost:9090"
ROOT = Path(__file__).resolve().parents[1]

VENDOR_CPU_QUERY = (
    "sum(rate(container_cpu_usage_seconds_total{"
    'job="cadvisor", container_label_com_docker_compose_service="vendor", image!=""'
    "}[1m]))"
)


def series(lo: float, hi: float, step: int = 15) -> list[tuple[float, float]]:
    r = httpx.get(
        f"{PROM}/api/v1/query_range",
        params={"query": VENDOR_CPU_QUERY, "start": str(lo), "end": str(hi), "step": str(step)},
        timeout=60.0,
    )
    data = r.json()
    if data.get("status") != "success" or not data["data"]["result"]:
        return []
    return [(float(t), float(v)) for t, v in data["data"]["result"][0]["values"]]


def main() -> None:
    timing = json.loads((ROOT / "benchmark_timing.json").read_text())
    for target_tps in (256, 4096):
        runs = sorted(
            (r for r in timing["runs"] if int(r["tps"]) == target_tps),
            key=lambda r: r["prometheus_timestamps"]["start_ms"],
        )
        lo = runs[0]["prometheus_timestamps"]["start_ms"] / 1000.0 - 60
        hi = runs[-1]["prometheus_timestamps"]["finish_ms"] / 1000.0
        pts = series(lo, hi, step=15)
        if not pts:
            print(f"tps={target_tps}: no CPU data")
            continue

        print(f"\n{'=' * 70}\ntps={target_tps}  vendor CPU (cores), t=-30s..+120s around each mode's start\n")
        for r in runs:
            mode = r["mode"]
            start = r["prometheus_timestamps"]["start_ms"] / 1000.0
            window = [(t - start, v) for t, v in pts if -30 <= t - start <= 120]
            vals = " ".join(f"{v:4.2f}" for _, v in window)
            print(f"{mode:20s} {vals}")


main()
