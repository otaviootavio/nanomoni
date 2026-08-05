"""Attribute a saturated run to one component, in one snapshot.

Runs on the host during the plateau of a benchmark:

    poetry run python scripts/probe-saturation.py [window_seconds]

Prints the rate the vendor is serving, the latency at that rate, the CPU each
container spends per payment, and the split of the Redis serving thread across
the commands it runs. The point is the per-payment column: a container at its
cpuset ceiling only says it ran out of cores, while CPU per payment says how much
of that ceiling one payment costs and therefore which component the next core
would help. `scripts/probe-worker-connections.py` covers the vendor's internal
split, which the container total also hides.

Redis command accounting resets `commandstats` and reads it back after the
window, so run this while traffic is steady -- a window that spans the start or
end of a run mixes the ramp into the averages.
"""

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# The metric names do not follow the mode names -- "paytree" is "paytree_std" on
# the wire and "signature" uses the unprefixed counter of the original payment
# router -- so both maps come from bench_plotter, which the plotters already read
# them from. A second copy here would be one more place to drift.
from bench_plotter.metric_queries import (
    LATENCY_BUCKET_METRIC_BY_MODE,
    PAYMENT_COUNTER_METRIC_BY_MODE,
)

PROMETHEUS = "http://localhost:9090/api/v1/query"
REDIS_CONTAINER = "nanomoni-redis-vendor-1"
SERVICES = ("vendor", "client", "redis-vendor", "issuer", "redis-issuer")

# A mode whose counter moves slower than this is residual traffic from a previous
# run being scraped, not the run under test.
MIN_RATE = 50.0


def query(expr):
    url = PROMETHEUS + "?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)["data"]["result"]


def scalar(expr):
    result = query(expr)
    if not result:
        return None
    value = float(result[0]["value"][1])
    return None if value != value else value  # NaN means no samples in the window


def rate_of(counter, window, *, succeeded):
    match = "=" if succeeded else "!="
    return scalar(f'sum(rate({counter}{{status{match}"success"}}[{window:g}s]))')


def detect_mode(window):
    """The mode whose payment counter is moving, and the rate it moves at."""
    rates = {}
    for mode, counter in PAYMENT_COUNTER_METRIC_BY_MODE.items():
        rate = rate_of(counter, window, succeeded=True)
        if rate is not None and rate > MIN_RATE:
            rates[mode] = rate
    if not rates:
        return None, 0.0
    return max(rates.items(), key=lambda item: item[1])


def container_cores():
    expr = (
        "sum by (container_label_com_docker_compose_service) "
        '(rate(container_cpu_usage_seconds_total{job="cadvisor",image!=""}[1m]))'
    )
    cores = {}
    for row in query(expr):
        service = row["metric"].get("container_label_com_docker_compose_service")
        if service in SERVICES:
            cores[service] = float(row["value"][1])
    return cores


def redis(*args):
    return subprocess.run(
        ["docker", "exec", REDIS_CONTAINER, "redis-cli", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def redis_info(section):
    values = {}
    for line in redis("info", section).splitlines():
        if ":" in line and not line.startswith("#"):
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def redis_commands():
    """calls and total microseconds per command, from cmdstat_ lines."""
    stats = {}
    for key, value in redis_info("commandstats").items():
        if not key.startswith("cmdstat_"):
            continue
        fields = dict(field.split("=", 1) for field in value.split(","))
        stats[key[len("cmdstat_") :]] = (int(fields["calls"]), float(fields["usec"]))
    return stats


WINDOW = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

redis("config", "resetstat")
cpu_before = redis_info("cpu")
time.sleep(WINDOW)
cpu_after = redis_info("cpu")
commands = redis_commands()

mode, rate = detect_mode(WINDOW)
if mode is None:
    print(f"no mode above {MIN_RATE:g} payments/s -- is a run in flight?")
    sys.exit(1)

counter = PAYMENT_COUNTER_METRIC_BY_MODE[mode]
print(f"window {WINDOW:g}s  mode {mode}  achieved {rate:.0f} payments/s")

# A payment the vendor rejected still cost it a request, and the client retries it,
# so CPU spent here never reaches the success counter above.
failed = rate_of(counter, WINDOW, succeeded=False)
if failed:
    print(f"rejected {failed:.0f} requests/s ({failed / (rate + failed):.1%} of all)")

buckets = LATENCY_BUCKET_METRIC_BY_MODE[mode]
quantiles = []
for quantile in (0.5, 0.95, 0.99):
    value = scalar(
        f"histogram_quantile({quantile}, sum(rate({buckets}[{WINDOW:g}s])) by (le))"
    )
    if value is not None:
        quantiles.append(f"p{int(quantile * 100)} {value:.1f} ms")
in_flight = scalar(f"sum({counter.removesuffix('_total')}_inprogress)")
if in_flight is not None:
    quantiles.append(f"in flight {in_flight:.0f}")
if quantiles:
    print("latency " + "  ".join(quantiles))

print(f"\n{'container':<14} {'cores':>7} {'µs/payment':>11}")
for service, cores in sorted(container_cores().items()):
    print(f"{service:<14} {cores:>7.2f} {cores / rate * 1e6:>11.0f}")


def delta(key):
    return float(cpu_after.get(key, 0.0)) - float(cpu_before.get(key, 0.0))


serving = (delta("used_cpu_user") + delta("used_cpu_sys")) / WINDOW
children = (delta("used_cpu_user_children") + delta("used_cpu_sys_children")) / WINDOW
print(
    f"\nredis serving thread {serving:.2f} of its 1.00 core ceiling"
    f" ({serving / rate * 1e6:.0f} µs/payment), children {children:.2f}"
)

print(
    f"\n{'command':<12} {'calls/s':>9} {'per payment':>12} {'µs/call':>9} {'cores':>7}"
)
for name, (calls, usec) in sorted(commands.items(), key=lambda item: -item[1][1]):
    if calls == 0:
        continue
    print(
        f"{name:<12} {calls / WINDOW:>9.0f} {calls / (rate * WINDOW):>12.2f} "
        f"{usec / calls:>9.1f} {usec / WINDOW / 1e6:>7.3f}"
    )
print(
    "\na command called from Lua is counted on its own and inside the EVALSHA that\n"
    "called it, so the cores column does not sum to the serving thread above"
)
