"""Map established vendor connections to the Uvicorn worker holding each one.

Runs inside the vendor container, where the connections live:

    docker cp scripts/probe-worker-connections.py nanomoni-vendor-1:/tmp/probe.py
    docker exec nanomoni-vendor-1 python /tmp/probe.py [cpu_window_seconds]

Prints one line per worker with the port it listens on, its pinned core, its CPU
utilization over a short window, and the connections it holds. Sampling it during
a run shows whether a client stays on one worker and how evenly load landed
across workers -- cadvisor only reports the container total, which hides a
saturated worker sitting next to an idle one. Connections from Prometheus
scraping /metrics show up here too, distinguishable by their peer address.
"""

import os
import re
import sys
import time

LISTEN = "0A"
ESTABLISHED = "01"


def _port(hex_addr):
    return int(hex_addr.split(":")[1], 16)


def read_tcp_table():
    """Listening ports and established connections, both keyed by socket inode."""
    listening = {}
    established = {}
    with open("/proc/net/tcp") as fh:
        next(fh)
        for line in fh:
            parts = line.split()
            local, remote, state, inode = parts[1], parts[2], parts[3], parts[9]
            if state == LISTEN:
                listening[inode] = _port(local)
            elif state == ESTABLISHED:
                established[inode] = (_port(local), remote)
    # Only connections served by a socket we are listening on; outbound
    # connections (Redis, issuer) share the table and are not interesting here.
    ports = set(listening.values())
    established = {i: v for i, v in established.items() if v[0] in ports}
    return listening, established


def worker_pids():
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                cmd = fh.read().decode(errors="replace")
        except OSError:
            continue
        if "spawn_main" in cmd or "nanomoni.main" in cmd:
            pids.append(entry)
    return sorted(pids, key=int)


def sockets_of(pid):
    found = set()
    fd_dir = f"/proc/{pid}/fd"
    try:
        entries = os.listdir(fd_dir)
    except OSError:
        return found
    for fd in entries:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            found.add(match.group(1))
    return found


def affinity_of(pid):
    try:
        return sorted(os.sched_getaffinity(int(pid)))
    except OSError:
        return []


def cpu_jiffies(pid):
    """utime + stime for a pid, or None if it went away."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            fields = fh.read().rsplit(") ", 1)[1].split()
    except (OSError, IndexError):
        return None
    return int(fields[11]) + int(fields[12])


CPU_WINDOW_S = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
HERTZ = os.sysconf("SC_CLK_TCK")

pids = worker_pids()
before = {pid: cpu_jiffies(pid) for pid in pids}
time.sleep(CPU_WINDOW_S)
after = {pid: cpu_jiffies(pid) for pid in pids}

listening, established = read_tcp_table()
total = 0
busy_total = 0.0
for pid in pids:
    held = sockets_of(pid)
    ports = sorted({listening[i] for i in held & listening.keys()})
    conns = [established[i] for i in held & established.keys()]
    start, end = before.get(pid), after.get(pid)
    busy = (
        (end - start) / HERTZ / CPU_WINDOW_S
        if start is not None and end is not None
        else float("nan")
    )
    if not ports and not conns:
        continue
    total += len(conns)
    busy_total += busy
    peers = ",".join(sorted(remote for _, remote in conns))
    listens = ",".join(str(p) for p in ports)
    print(
        f"worker pid={pid} port={listens} core={affinity_of(pid)} "
        f"busy={busy:5.0%} conns={len(conns)} peers={peers}"
    )
print(
    f"total established connections = {total}, "
    f"summed worker CPU = {busy_total:.2f} cores over {CPU_WINDOW_S:g}s"
)
