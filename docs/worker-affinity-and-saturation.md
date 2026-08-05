# Worker Affinity and the Saturation Layout

How a client is bound to a single vendor worker, why that binding had to be made
explicit, and what it exposed underneath. Every number here was measured on the
bench box with `run_tps_saturation_sweep.sh` at a target of 8192 or 16384 TPS
across the five payment modes, or with a single-mode run instrumented directly.
The core layout itself is described in [`tuning.md`](../tuning.md); this document
covers the change and the evidence behind it.

The starting question was how to make a client's HTTP traffic always reach the
same worker. Answering it moved the measured ceiling from ~3900 to 9.0-10.4k TPS
on four of the five modes, because the mechanism that provides affinity is also
the mechanism that distributes load, and it was distributing it badly.

Read this document for the mechanisms and the evidence. For where the system ends
up — which component holds each mode, what a payment costs, and what the two
remaining barriers require — read
[benchmark-ceiling-and-what-remains.md](benchmark-ceiling-and-what-remains.md).

---

## 1. A connection already belongs to one worker

**Mechanism:** each Uvicorn worker accepts its own connections and serves every
request on a connection in its own event loop. HTTP keep-alive therefore *is*
worker affinity, and the vendor holds idle connections for 120s
(`KEEP_ALIVE_TIMEOUT_SEC` in `src/nanomoni/main.py`). Nothing needs to be added
at the server for a *connection* to stay on a worker.

**What defeated it:** `run_client_flow` created one `VendorClientAsync` per
process and shared it across every virtual client in that process. Its
`aiohttp.ClientSession` pool is keyed by host, not by caller, so a virtual client
about to send its next payment took whichever connection was free. Consecutive
payments on the same channel left over different connections, i.e. reached
different workers.

**Change:** one dedicated `VendorClientAsync` per virtual client, its pool capped
at a single connection (`connection_limit=1` →
`aiohttp.TCPConnector(limit=1, keepalive_timeout=120)` in
`src/nanomoni/infrastructure/http/http_client.py`). The keep-alive value mirrors
the server's on purpose: aiohttp's 15s default would drop an idle connection and
the reconnect would be accepted by whatever worker won the race, silently undoing
the affinity.

**Verification:** a 60s payword run with 20 virtual clients, sampling every 5s
which worker held which connection (`scripts/probe-worker-connections.py`):
**0 of the connections changed worker.** The 23 connections seen at the start are
20 dedicated ones plus one bootstrap connection per client process (used only to
fetch the vendor public key); the bootstrap ones drop out after aiohttp's default
15s idle, leaving exactly 20.

---

## 2. A shared accept socket does not balance

**What the affinity exposed:** with each client pinned to the worker that
accepted it, *which* worker accepted it started to matter. Uvicorn's multi-worker
mode has all workers accept from one shared listening socket and lets the kernel
pick, and that is not round-robin — the worker quickest to accept keeps winning,
so a burst of connections piles onto a few of them.

Measured under `paytree` with 40 virtual clients and 10 workers, one core each:

| core | connections | worker CPU |
|---|---|---|
| 10 | 7 | 91% |
| 9 | 7 | 90% |
| 6 | 6 | 89% |
| 8 | 5 | 84% |
| 7 | 4 | 71% |
| 2 | 4 | 67% |
| 5 | 3 | 57% |
| 4 | 2 | 18% |
| 1 | 1 | 9% |
| 3 | 1 | 8% |

Seven workers were at or near the ceiling of their single core while two sat
below 10%. The aggregate hid it completely: cadvisor reported 5.5 of 10 cores,
which reads as "half idle" and is really "some workers saturated, some idle".
This is why doubling the virtual clients from 20 to 40 moved `paytree` by 0.1% —
the new clients piled onto the same skewed distribution. In the 20-client run the
spread was worse still: 20 connections on 5 of the 10 workers.

**Change:** one listening socket per worker. `src/nanomoni/main.py` runs
`VENDOR_API_WORKERS` single-worker servers on consecutive ports from
`VENDOR_API_PORT` (8000..8009) instead of Uvicorn's shared-socket mode, each
pinned to its own core by the existing `VENDOR_PIN_WORKERS_TO_CORES`; a worker
dying takes the set down, since a container missing one port would silently drop
the traffic aimed at it. The generator picks its port from its own identity:
`vendor_url_for_worker(base_url, index, port_count)` in
`src/nanomoni/client/common.py`, using the client's *global* index in
`CLIENT_PRIVATE_KEY_PEMS` so that several client processes each taking a slice
still add up to an even spread.

**Verification:** the same 40-client `paytree` run afterwards: exactly **4
connections per worker** (5 on port 8000, which also serves Prometheus), every
worker between **81% and 91%**, summing to **8.59 of 10 cores** against 5.85
before.

---

## 3. Redis was spending its core on AOF rewrite, not on payments

**Per-payment cost.** The payment path is already tight: 2 round-trips, one
`MGET` for the channel and its state or nodes, then one `EVALSHA` whose Lua
script performs every write atomically (see
`src/nanomoni/infrastructure/scripts.py`). Measured on `paytree_child_pair` from
`INFO commandstats`, at 4733 payments/s on an accumulated keyspace:

| command | per payment | µs/call |
|---|---|---|
| `MGET` | 1 | 3.1 |
| `EVALSHA` | 1 | 76.9 |
| `SET` (inside the script) | 5 | 1.9 |
| `ZADD` (inside the script) | 2 | 6.0 |
| `GET` (inside the script) | 1 | 1.0 |

The inner calls are *included* in the `EVALSHA` figure, and account for ~23 µs of
its 77 µs; the rest is script-level work. Adding what Redis spends outside
command execution gives ~105 µs of process CPU per payment.

**The discrepancy.** cadvisor showed the `redis-vendor` cgroup at 0.86-0.96 of
its single core, which is what first suggested Redis as the next ceiling. But
`INFO` reported the `redis-server` process using only 0.49 core. Listing
processes by core during a run resolved it: **two `redis-server` processes on
core 11**, ~0.5 core each, the second one present only while the run was in
flight. It is the AOF rewrite child — a `fork`, so it inherits the cgroup and
therefore the same single core, competing head to head with the one thread that
serves payments. Core 11 was pegged at 100% (63% user, 23% system, 14% softirq).

**Why it never stopped rewriting.** Nothing deletes keys after a run, so the
keyspace had grown to 15.3M keys and 3.89 GB across runs, with the AOF at 3.45 GB
over a base of 1.97 GB. With `auto-aof-rewrite-percentage` at its default a
rewrite fires every time the file doubles, so under load it was almost always
running. The accumulation cost more than the rewrites: on an empty keyspace the
same `EVALSHA` takes **36 µs instead of 72**.

**Change:** `redis-vendor` gets a second core (`cpuset: "11,18"`), taken from the
monitoring block (now `19-23`) rather than from the vendor or the generator,
which are in the measured path — and landing in another L3 is desirable, since
the rewrite streams the whole dataset and would otherwise evict the serving
thread's cache. `run_tps_saturation_sweep.sh` flushes both datastores before
every run, so no mode inherits the keyspace of the modes before it.

**Verification:** `paytree_child_pair` at **8120 payments/s** (was 4733), the
rewrite child on core 18 at 35%, core 11 down to 84%, and the serving process
holding 0.85 core instead of 0.49.

One operational note: an AOF that size also costs ~60s of container startup
before Redis will answer, which is worth knowing when a restart looks hung.

---

## 4. What the sweep measured at each step

Achieved TPS against a target of 8192, five modes:

| mode | baseline (16 clients, shared pool and socket) | 40 clients, shared socket | 40 clients, port per worker | + 2-core Redis and per-run flush |
|---|---|---|---|---|
| payword | 3919.0 | 5321.9 | 7247.0 | **8150.9** (99.5%) |
| paytree | 3840.5 | 5380.2 | 6837.9 | **8117.0** (99.1%) |
| paytree_first_opt | 3308.6 | 5212.3 | 6542.7 | **8038.2** (98.1%) |
| paytree_child_pair | 3847.4 | 4802.8 | 5293.3 | **8027.2** (98.0%) |
| signature | 2111.7 | 4424.2 | 5767.0 | 6271.2 (76.6%) |

The baseline column comes from the sweep that preceded this work; several things
differ in it besides the connection handling (virtual-client count and core
layout among them), so it marks where the measurement started rather than
isolating one change. The last two columns differ only in the Redis changes.

---

## 5. Configuration surface

| Variable | Where | Meaning |
|---|---|---|
| `VENDOR_API_WORKERS` | `envs/vendor.env.sh` | Number of single-worker servers, and therefore of ports used from `VENDOR_API_PORT` upward |
| `VENDOR_PIN_WORKERS_TO_CORES` | `envs/vendor.env.sh` | Each worker claims one core of the container `cpuset` for its lifetime |
| `CLIENT_PROCESSES` | `envs/client.env.sh` | Client processes to split the virtual clients over |
| `CLIENT_PIN_PROCESSES_TO_CORES` | `envs/client.env.sh` | Same core-claiming for the generator's processes |
| `CLIENT_VENDOR_PORT_COUNT` | `envs/client.env.sh` | Consecutive vendor ports to spread virtual clients over; `1` disables spreading |

Three invariants hold this together, and breaking any of them degrades quietly
rather than failing:

- `CLIENT_VENDOR_PORT_COUNT` must equal `VENDOR_API_WORKERS`, or some workers
  receive no traffic.
- `CLIENT_VIRTUAL_CLIENTS` should be a multiple of it, or some workers carry an
  extra client and cap the measured ceiling.
- The `cpuset` must hold at least `VENDOR_API_WORKERS` cores; surplus workers are
  left unpinned rather than doubled up, and the startup log says which core each
  worker took.

On the host, only port 8000 is published. The rest of the range would collide
with the issuer on 8001 and the client's metrics on 8002, and nothing needs them
from outside: the generator dials `vendor:800N` over the compose network, and
Prometheus keeps scraping `:8000`, where `/metrics` aggregates every worker
through `PROMETHEUS_MULTIPROC_DIR`. The same collision applies to running the
vendor directly on the host, which is why the local-dev and example env scripts
keep `VENDOR_API_WORKERS=1`.

---

## 6. The ceiling at a target of 16384

Four of the five modes finished within 2% of the 8192 target, so the target held
them rather than the system. Raising `TPS_VALUES` to 16384 located the knee:

| mode | achieved TPS | ratio of target |
|---|---|---|
| payword | 10368.4 | 63.3% |
| paytree | 9267.7 | 56.6% |
| paytree_child_pair | 9159.6 | 55.9% |
| paytree_first_opt | 9009.6 | 55.0% |
| signature | 6219.5 | 38.0% |

`signature` went from 6271 to 6219 when the target doubled. The generator binds
it (2.56 of the client's 3 cores against 3.52 of the vendor's 10), so the target
does not reach it — the failure mode that the 3:1 vendor-to-client core rule in
`tuning.md` exists to prevent.

A `paytree_first_opt` run instrumented during its plateau gives the shape of the
ceiling for the other four:

| component | CPU | against its cpuset |
|---|---|---|
| vendor, 10 workers | 9.80 cores | 98% on each of 10 |
| client, 3 processes | 2.79 cores | 93% of 3 |
| redis-vendor | 1.15 cores | 58% of 2 |

Each worker held 4 connections, except port 8000 with 5, which also serves
Prometheus. The vendor spends 1.02 ms of CPU per payment, the generator 291 µs,
Redis 120 µs across its two cores. Latency during the same window: p50 2.4 ms,
p95 3.3 ms, p99 4.9 ms, 23 payments in flight.

A p99 of 4.9 ms at 98% CPU puts this at a throughput ceiling rather than at a
queue collapse, and the distribution matches what section 2 set out to produce.
The generator trails the vendor by 5 points, so a core given to one side without
the other moves the binding component instead of the ceiling.

---

## 7. Five walls, and where each one lives

Every ceiling in this document announced itself through one signal — an aggregate
near its limit — and the cause differed each time.

| # | ceiling | reading at the time | cause |
|---|---|---|---|
| 0 | 3900 | server capacity | the shared `aiohttp` pool spread one channel's payments over several workers |
| 1 | 5300 | vendor at 5.5 of 10 cores, half idle | shared accept socket: 7 workers at the ceiling of their core, 2 under 10% |
| 2 | 5300-6800 | `redis-vendor` at 0.96 of one core, single-threaded | the serving thread used 0.49; the AOF rewrite child took the rest of the core, and the keyspace left by earlier runs moved `EVALSHA` from 36 to 72 µs |
| 3 | 8100 | system capacity | `TPS_VALUES=8192`, with four modes delivering 98-99.5% of it |
| 4 | 9000-10400 | vendor saturated again | the vendor saturates: 10 cores at 98%, 1.02 ms of CPU per payment |

Walls 0 and 1 hold load away from capacity that exists. Wall 2 spends
capacity on work outside the measured path — the rewrite child burns a core on
the keyspace that earlier runs left behind. Wall 3 comes from a constant in a
shell script. Wall 4 reports the cost of a payment.

So four of the five describe the harness, and `signature` at 6219 joins them,
since it measures the generator. Walls 1 and 2 also share a mechanism: a cgroup
total hides the distribution inside it, and in both cases the container sat at
its limit while the process doing the work did not. Doubling the virtual clients
from 20 to 40 moved `paytree` by 0.1% (section 2) — the intervention followed the
aggregate and missed the cause. Section 11 lists the commands that open the
aggregate up, per worker, per command and per core.

---

## 8. Two loops, and what ends each one

Removing interference forms the first loop. Walls 0, 1 and 2 changed which
hardware paid for a payment, or removed a cost that the design does not impose —
the 72 µs `EVALSHA` of section 3 returns to 36 µs on a keyspace that holds one
run. Neither kind touches what the design itself costs. That loop carried the
ceiling from 3900 to 8100 on the same 24 cores, each fix holds for every run
after it, and the loop terminates: the defects run out, and what the ceiling
reports then is the cost of the design.

Buying cores forms the second loop. It leaves the cost per payment where it is
and raises the ceiling by widening a cpuset. On a fixed box it takes from a
neighbour, and the 3:1 rule couples the two sides: a core for the vendor draws
1.33 cores, because the generator grows with it or binds first. This loop ran
once, when `redis-vendor` took core 18 from the monitoring block, and that round
mixed both loops — the core was a purchase, the per-run `flushall` removed
interference, and the jump from 4733 to 8120 on `paytree_child_pair` covers the
two together.

The monitoring block holds 5 cores and uses 0.1 of them. Spending all 5 puts the
vendor at 14 cores and the generator at 4, which the per-payment costs in section
6 turn into 13.7k TPS on either side. The serving thread of `redis-vendor` caps
that number: one thread executes every command, a payment costs it ~105 µs, and
the four paytree and payword modes run between 9.0k and 10.4k. These two
figures come from arithmetic over the measurements above; no run has held 14
vendor cores.

The second loop therefore has one round left, and the wall behind it takes no
cores. What follows it changes the design: the round-trip count per payment, the
writes the script performs, or a keyspace shard that removes the single serving
thread. Reporting CPU per payment instead of TPS also ends the loop, by stating a
number that the size of the box does not set. Section 9 spends part of that round
and reports which of these the ceiling turns out to follow.

---

## 9. Spending the round: 12 vendor cores and 4 generator cores

Section 8 projects that the serving thread of `redis-vendor` caps the next round
of core buying. Spending 3 of the monitoring block's 5 cores tests it. The vendor
moved from `1-10` to `1-10,19-20` with `VENDOR_API_WORKERS=12`, the generator from
`12-14` to `12-14,21` with `CLIENT_PROCESSES=4`, `CLIENT_VENDOR_PORT_COUNT=12` and
48 virtual clients, so the 3:1 rule holds at 12:4 and every worker takes 4
clients. Monitoring kept `22-23`. Cores 19-20 belong to another L3 than `1-10`,
which the workers absorb: each one is a process with its own connection and its
own working set.

The same sweep at the same target of 16384:

| mode | 10 vendor / 3 generator | 12 vendor / 4 generator | change |
|---|---|---|---|
| payword | 10368.4 | 12557.6 | +21% |
| paytree | 9267.7 | 11688.5 | +26% |
| paytree_first_opt | 9009.6 | 9761.4 | +8% |
| paytree_child_pair | 9159.6 | 9672.9 | +6% |
| signature | 6219.5 | 7806.6 | +26% |

`scripts/probe-saturation.py` sampled each plateau for what holds it:

| mode | plateau TPS | vendor | generator | redis serving thread | redis µs/payment |
|---|---|---|---|---|---|
| payword | 12753 | 11.85/12 | 3.56/4 | 0.96 | 75 |
| paytree | 11909 | 7.74/12 | 2.51/4 | 0.91 | 76 |
| paytree_child_pair | 10020 | 10.10/12 | 2.86/4 | 1.01 | 100 |
| paytree_first_opt | 9299 | 10.48/12 | 2.98/4 | 0.98 | 106 |
| signature | 8190 | 11.97/12 | 2.27/4 | 0.20 | 65 |

The projection holds for the four paytree and payword modes. The serving thread
runs between 0.91 and 1.01 of the one core it can use, and each ceiling sits at
the inverse of what a payment costs it: 75 µs allows 13.3k and payword reached
12.6k, 106 µs allows 9.4k and first_opt reached 9.8k. Two extra vendor cores moved
first_opt by 8% and child_pair by 6% while the vendor left 12-16% of its cores
unused, which is how a component that takes no cores reads from outside.

What the script writes explains the order of the modes. `paytree` and `payword`
issue 3 `SET`s per payment and their `EVALSHA` costs 24 µs; `paytree_child_pair`
and `paytree_first_opt` issue 5 `SET`s and 2 `ZADD`s, and their `EVALSHA` costs 37
and 43 µs. The ranking the sweep reports per scheme therefore reduces to the
number of keys that scheme's script writes.

`signature` moved for the other reason. The vendor holds 11.97 of 12 cores while
Redis stays at 0.20, so verifying a signature is what limits it, and the 2 cores
went to the component that was short. Section 6 records 3.52 of 10 vendor cores at
6271 TPS for this mode, which is 561 µs per payment against the 1533 µs measured
here. Three sources agree on the figure measured here — `mpstat` per core, the
in-container probe, and cadvisor — and the earlier one does not reproduce.

Latency separates the two situations. payword spreads its work over three
components at 89-99% and holds p99 at 2.9 ms. first_opt funnels through one thread
at 0.98 and sits at p50 3.5 ms with p99 11.9 ms: the queue in front of a component
that runs one command at a time.

One entry in section 8 needs correcting against this: the remaining monitoring
cores buy nothing for `paytree_first_opt` and `paytree_child_pair`, so the second
loop has less runway than the core arithmetic offers, and for those two it ended
here. A second figure to drop is the 11 KB per payment once attributed to
first_opt, which came from a window where its `MGET` cost 68 µs; on these plateaus
that `MGET` costs 2.5 µs, and the write count above carries the difference between
the modes instead.

---

## 10. Where the vendor spends its own CPU

Section 9 leaves the vendor holding 11.97 of 12 cores in `signature` and 10.0 to
10.5 in the other four modes, so the cost of a payment inside the vendor bounds
what relieving Redis can buy. The plotter already measures this: `profiling/
aggregate.py` reads the merged Pyroscope profile over each run's plateau and writes
`profile_macro_micro_table.csv` — the vendor's total CPU, the part under that mode's
endpoint handler, and the crypto and Redis parts inside the handler — plus one flame
graph per mode. The saturation report runs that same stage now, so a sweep aimed at
a ceiling produces the attribution of that ceiling in the same directory.

Shares of the vendor's total CPU, from the run in section 9:

| mode | above the handler | inside it | crypto | redis | unattributed inside |
|---|---|---|---|---|---|
| paytree | 55.4% | 44.6% | 7.6% | 29.7% | 6.9% |
| paytree_child_pair | 57.6% | 42.4% | 1.8% | 27.3% | 12.6% |
| paytree_first_opt | 56.6% | 43.4% | 2.3% | 26.7% | 13.7% |
| payword | 58.6% | 41.4% | 1.8% | 31.4% | 7.6% |
| signature | 54.4% | 45.6% | 19.9% | 19.2% | 6.3% |

Above the handler sits the ASGI path: HTTP parsing, routing, dependency
resolution, response serialization, the event loop. It takes more CPU than the
Redis calls in every mode, and more than signature verification in the mode that
verifies signatures. So the framework sets the floor for four of the five schemes,
and the two cores section 9 moved to the vendor spent over half of themselves
there.

The flame graphs name what fills that path. The widest frames by self time are
CPython's own — `_PyEval_EvalFrameDefault`, `_PyFunction_Vectorcall`,
`_PyType_Lookup` — both above the handler and inside it, which is also what the
unattributed column above is made of. The vendor runs Python 3.9 (`pyproject.toml`
pins `>=3.9,<3.10.0`), so the specializing interpreter of 3.11 and later has never
been under this measurement.

---

## 11. Reproducing the measurements

One snapshot that attributes a plateau — rate, latency, CPU per payment per
container, the Redis serving thread against its one-core ceiling, and the command
split inside it:

```sh
poetry run python scripts/probe-saturation.py 12   # 12s window
```

It resets `commandstats`, so run it while traffic is steady: a window that spans
the start or end of a run mixes the ramp into every average. It also detects the
mode from the counter that is moving, which spares one trap — the counter names do
not follow the mode names. `paytree` increments `paytree_std_payment_requests_total`
and `signature` increments the unprefixed `payment_requests_total`, so a query
written from the mode name returns an empty result and reads as an idle system.

The pieces it is built from, for when only one of them is needed.

Per-worker connections and CPU — the split cadvisor's container total hides:

```sh
docker cp scripts/probe-worker-connections.py nanomoni-vendor-1:/tmp/probe.py
docker exec nanomoni-vendor-1 python /tmp/probe.py 6   # 6s CPU window
```

Redis command accounting, around a steady-state window of a running benchmark:

```sh
docker exec nanomoni-redis-vendor-1 redis-cli config resetstat
sleep 40
docker exec nanomoni-redis-vendor-1 redis-cli info commandstats
docker exec nanomoni-redis-vendor-1 redis-cli info stats   # used_cpu_user/sys, net bytes
```

Remember that a command called from Lua is counted in `commandstats` on its own
*and* inside the `EVALSHA` that called it, so the two cannot be added.

Per-core utilization and per-process CPU, from `sysstat`:

```sh
mpstat -P 1-14,18-21 5 1   # %usr / %sys / %soft per core
pidstat -p ALL 5 1         # which process is burning which core
```

The charts, the ceiling per mode, and the CPU attribution of section 10, from a
sweep's timing file:

```sh
poetry run python -m bench_plotter.saturation tps_saturation_timing.json
```

Per-container CPU, from cadvisor through Prometheus:

```sh
curl -sg "http://localhost:9090/api/v1/query" --data-urlencode \
  'query=sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{job="cadvisor",image!=""}[1m]))'
```

Dividing the CPU of a container by the rate gives the per-payment cost that
sections 8 and 9 reason from, and it holds across machine sizes where TPS does
not. Cross-check any container reading that decides something: `docker stats
--no-stream` reported the vendor at 6.6% of one core during the section 9 runs
while `mpstat`, the in-container probe and cadvisor all put it above 11 cores.
