"""Re-fetch the vendor Redis memory series behind
vendor_redis_memory_delta_bytes_per_payments_vs_total_payments.png and
characterise each run's curve, so the oscillation can be attributed to the
data (dataset size) or to the measurement (window/series selection).

Read-only: queries Prometheus, writes nothing back.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

PROM = "http://localhost:9090"
MEM_EXPR = (
    "container_memory_working_set_bytes{"
    'container_label_com_docker_compose_service="redis-vendor", image!=""'
    "} / 1024 / 1024"
)
RSS_EXPR = (
    "container_memory_rss{"
    'container_label_com_docker_compose_service="redis-vendor", image!=""'
    "}  / 1024 / 1024"
)
CACHE_EXPR = (
    "container_memory_cache{"
    'container_label_com_docker_compose_service="redis-vendor", image!=""'
    "} / 1024 / 1024"
)
BYTES_PER_MIB = 1024.0 * 1024.0
DRAIN_SEC = 180.0


def query_range(expr: str, start: float, end: float, step: str = "5s"):
    qs = urllib.parse.urlencode(
        {"query": expr, "start": str(start), "end": str(end), "step": step}
    )
    with urllib.request.urlopen(f"{PROM}/api/v1/query_range?{qs}", timeout=60) as r:
        payload = json.load(r)
    if payload.get("status") != "success":
        raise RuntimeError(payload)
    return payload["data"]["result"]


def series_points(result):
    """[(labels, [(ts, value), ...]), ...] in the order Prometheus returned them."""
    out = []
    for s in result:
        pts = [(float(t), float(v)) for t, v in s["values"]]
        out.append((s.get("metric", {}), pts))
    return out


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def plot(rows, out_path: str) -> None:
    """Peak-based (what the sweep charts) vs plateau-based (settled dataset)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    modes = ["paytree_first_opt", "paytree_child_pair"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = {"paytree_first_opt": "tab:green", "paytree_child_pair": "tab:pink"}
    for mode in modes:
        pts = sorted((r["reqs"], r) for r in rows if r["mode"] == mode)
        x = [p[0] for p in pts]
        ax.plot(
            x,
            [p[1]["peak"] for p in pts],
            "-o",
            color=colors[mode],
            label=f"{mode} — max-min (charted today)",
        )
        ax.plot(
            x,
            [p[1]["plat"] for p in pts],
            "--s",
            color=colors[mode],
            alpha=0.55,
            label=f"{mode} — settled dataset",
        )
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Total payments")
    ax.set_ylabel("Redis memory delta (bytes / payment)")
    ax.set_title("Peak-based delta oscillates; the settled dataset does not")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    print(f"\nwrote {out_path}")


def main(timing_path: str) -> None:
    timing = json.load(open(timing_path))
    print(f"run_ts={timing['server_run_timestamp']}\n")
    rows = []

    hdr = (
        f"{'mode':20s} {'reqs':>8s} {'vc':>3s} | "
        f"{'min':>7s} {'max':>8s} {'plateau':>8s} | "
        f"{'peak-B/pay':>10s} {'plat-B/pay':>10s} {'spike%':>7s}"
    )
    print(hdr)
    print("-" * len(hdr))

    for run in timing["runs"]:
        ts = run["prometheus_timestamps"]
        start, end = ts["start_ms"] / 1000.0, ts["finish_ms"] / 1000.0
        result = query_range(MEM_EXPR, start, end)
        allser = series_points(result)
        if not allser:
            print(f"{run['mode']:20s} {run['total_requests']:8d}   -- no data")
            continue

        # The plotter reduces with charts[0] only -- mirror that exactly.
        _labels, pts = allser[0]
        vals = [v for _, v in pts]
        lo, hi = min(vals), max(vals)

        # The last third of DRAIN_SEC: traffic and settlement are both long
        # over, so this is the dataset Redis is actually left holding.
        tail = [v for t, v in pts if t >= end - DRAIN_SEC / 3.0]
        plateau = median(tail) if tail else vals[-1]

        reqs = run["total_requests"]
        peak_per_pay = (hi - lo) * BYTES_PER_MIB / reqs
        plat_per_pay = (plateau - lo) * BYTES_PER_MIB / reqs
        spike_pct = (hi - plateau) / plateau * 100.0 if plateau else 0.0

        print(
            f"{run['mode']:20s} {reqs:8d} {run.get('virtual_clients', 1):3d} | "
            f"{lo:7.2f} {hi:8.1f} {plateau:8.1f} | "
            f"{peak_per_pay:10.0f} {plat_per_pay:10.0f} {spike_pct:6.0f}%"
        )
        rows.append(
            {
                "mode": run["mode"],
                "reqs": reqs,
                "peak": peak_per_pay,
                "plat": plat_per_pay,
            }
        )

    plot(rows, f"plots/{timing['server_run_timestamp']}/_oscillation_diagnosis.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "benchmark_timing.json")
