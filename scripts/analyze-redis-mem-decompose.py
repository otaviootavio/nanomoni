"""Decompose the redis-vendor cgroup memory behind the oscillating
paytree_first_opt points into RSS (the Redis dataset) vs page cache (the AOF
file), plus the container's own AOF file size on disk.

Read-only: queries Prometheus, writes nothing back.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

PROM = "http://localhost:9090"
SEL = 'container_label_com_docker_compose_service="redis-vendor", image!=""'
MIB = 1024.0 * 1024.0
DRAIN_SEC = 180.0

METRICS = {
    "wss": f"container_memory_working_set_bytes{{{SEL}}}",
    "rss": f"container_memory_rss{{{SEL}}}",
    "cache": f"container_memory_cache{{{SEL}}}",
    "active_file": f"container_memory_total_active_file_bytes{{{SEL}}}",
    "inactive_file": f"container_memory_total_inactive_file_bytes{{{SEL}}}",
    "fs_usage": f"container_fs_usage_bytes{{{SEL}}}",
}


def query_range(expr, start, end, step="5s"):
    qs = urllib.parse.urlencode(
        {"query": expr, "start": str(start), "end": str(end), "step": step}
    )
    with urllib.request.urlopen(f"{PROM}/api/v1/query_range?{qs}", timeout=60) as r:
        payload = json.load(r)
    if payload.get("status") != "success":
        raise RuntimeError(payload)
    res = payload["data"]["result"]
    if not res:
        return {}
    return {float(t): float(v) / MIB for t, v in res[0]["values"]}


def dump(run, every=4):
    ts = run["prometheus_timestamps"]
    start, end = ts["start_ms"] / 1000.0, ts["finish_ms"] / 1000.0
    traffic_end = end - DRAIN_SEC
    cols = {k: query_range(e, start, end) for k, e in METRICS.items()}
    stamps = sorted(cols["wss"])

    print(f"\n### {run['mode']}  reqs={run['total_requests']}  vc={run.get('virtual_clients')}")
    print(f"{'t(s)':>7s} {'wss':>9s} {'rss':>9s} {'cache':>9s} {'act_f':>9s} {'inact_f':>9s} {'fs_used':>9s}  phase")
    prev_wss = None
    for i, t in enumerate(stamps):
        wss = cols["wss"].get(t)
        drop = prev_wss is not None and prev_wss - wss > 1.0
        prev_wss = wss
        # Print a coarse sample, but never skip a step where wss collapsed.
        if i % every and not drop:
            continue
        phase = "traffic" if t <= traffic_end else "DRAIN"
        if drop:
            phase += "  <-- DROP"
        print(
            f"{t - start:7.0f} "
            f"{wss:9.1f} {cols['rss'].get(t, float('nan')):9.1f} "
            f"{cols['cache'].get(t, float('nan')):9.1f} "
            f"{cols['active_file'].get(t, float('nan')):9.1f} "
            f"{cols['inactive_file'].get(t, float('nan')):9.1f} "
            f"{cols['fs_usage'].get(t, float('nan')):9.1f}  {phase}"
        )


def main(timing_path: str, wanted: set[tuple[str, int]]) -> None:
    timing = json.load(open(timing_path))
    for run in timing["runs"]:
        if (run["mode"], run["total_requests"]) in wanted:
            dump(run)


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "benchmark_timing.json",
        {
            ("paytree_first_opt", 38400),
            ("paytree_child_pair", 38400),
            ("paytree_first_opt", 153600),
            ("paytree_first_opt", 1228800),
            ("paytree_child_pair", 1228800),
        },
    )
