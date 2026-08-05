# Where the benchmark stops, and what would move it

This closes the round of work that
[worker-affinity-and-saturation.md](worker-affinity-and-saturation.md) records. That
document follows the investigation in the order it happened, from the first ceiling
at 3900 TPS to the current one, and holds the derivation of every number below. This
one states where the system stands, which component holds each mode, and what each
remaining barrier requires from whoever picks this up.

The layout under measurement: an AMD EPYC 9224, 24 physical cores, one uvicorn
worker per vendor core on its own listening port, one Redis per side, the load
generator pinned beside them. [tuning.md](../tuning.md) holds the core map and the
host-level tuning.

---

## 1. What holds each mode

Sustained rates from a sweep at a target of 16384 TPS, and the plateau of that same
sweep sampled by `scripts/probe-saturation.py`:

| mode | sustained TPS | plateau TPS | vendor | generator | redis serving thread | vendor µs/payment |
|---|---|---|---|---|---|---|
| payword | 12557.6 | 12753 | 11.85/12 | 3.56/4 | 0.96 | 929 |
| paytree | 11688.5 | 11909 | 7.74/12 | 2.51/4 | 0.91 | 650 |
| paytree_first_opt | 9761.4 | 9299 | 10.48/12 | 2.98/4 | 0.98 | 1127 |
| paytree_child_pair | 9672.9 | 10020 | 10.10/12 | 2.86/4 | 1.01 | 1008 |
| signature | 7806.6 | 8190 | 11.97/12 | 2.27/4 | 0.20 | 1462 |

The serving thread of `redis-vendor` executes every command on one core, and it
holds the four paytree and payword modes: between 0.91 and 1.01 of the one core it
can use, with the vendor leaving between 0.2 and 4.3 cores unused behind it.
`signature` is the exception — Redis sits at 0.20 while the vendor holds 11.97 of 12 cores, so
verifying a signature is what limits it.

Each ceiling sits at the inverse of what a payment costs the serving thread: 75 µs
allows 13.3k and payword reached 12.6k, 106 µs allows 9.4k and `first_opt` reached
9.8k. What the Lua script writes sets that cost. `paytree` and `payword` issue 3
`SET`s per payment and their `EVALSHA` costs 24 µs; `paytree_child_pair` and
`paytree_first_opt` issue 5 `SET`s and 2 `ZADD`s, and their `EVALSHA` costs 37 and
43 µs. The ranking the sweep reports per scheme reduces to the number of keys that
scheme's script writes.

Latency separates the two situations. payword spreads its work over three components
at 89-99% and holds p99 at 2.9 ms. `first_opt` funnels through one thread at 0.98
and sits at p50 3.5 ms with p99 11.9 ms — the queue in front of a component that
runs one command at a time.

---

## 2. The core budget is spent

All 24 physical cores carry an assignment: the vendor's twelve workers on
`1-10,19-20`, its Redis on `11,18`, the generator's four processes on `12-14,21`, the
issuer on `16` beside its Redis on `17`, monitoring on `22-23`, and `0` plus `15` for
housekeeping and interrupts. What remains unassigned is the SMT siblings at `N+24`,
which share execution units with the core they sit on, so they do not add a core to
give.

Two constraints close the arithmetic. The 3:1 vendor-to-generator rule means a core
given to the vendor draws 1.33 cores, because the generator grows with it or binds
first — `signature` at 6219 TPS was a generator reading, not a server one. And the
two cores left in the monitoring block buy nothing for `paytree_first_opt` or
`paytree_child_pair`, which already leave vendor cores idle while queueing on one
Redis thread.

So the loop that raises the ceiling by widening a cpuset ended on this box. The last
round of it moved three cores and bought 21-26% for payword, paytree and signature
while paying 8% and 6% for the two modes that were already Redis-bound.

---

## 3. What a payment costs the vendor

The plotter's profiling stage reads the merged Pyroscope profile over each run's
plateau and writes `profile_macro_micro_table.csv`. Applying its shares to the CPU
per payment above gives where a payment's microseconds go inside the vendor. The
shares come from the middle 70% of the run and the totals from a 12s plateau window,
so the split assumes the mix holds across the plateau.

| mode | µs/payment | above the handler | crypto | redis calls | unattributed inside |
|---|---|---|---|---|---|
| payword | 929 | 544 | 16 | 292 | 70 |
| paytree | 650 | 360 | 49 | 193 | 45 |
| paytree_child_pair | 1008 | 581 | 18 | 276 | 127 |
| paytree_first_opt | 1127 | 637 | 26 | 301 | 154 |
| signature | 1462 | 795 | 290 | 281 | 93 |

Above the handler sits the ASGI path: HTTP parsing, routing, dependency resolution,
response serialization, the event loop. It takes more CPU than the Redis calls in
every mode, and more than signature verification in the mode that verifies
signatures. The flame graphs name what fills it — the widest frames by self time are
CPython's own, `_PyEval_EvalFrameDefault`, `_PyFunction_Vectorcall`,
`_PyType_Lookup`, both above the handler and inside it, which is also what the
unattributed column is made of. The vendor runs Python 3.9 (`pyproject.toml` pins
`>=3.9,<3.10.0`), so the specializing interpreter of 3.11 and later has never been
under this measurement.

---

## 4. Two barriers remain, and they differ in kind from the earlier ones

Five ceilings preceded these, and four of them were interference: load held away
from capacity that existed, or CPU spent outside the measured path. The shared
`aiohttp` pool spread one channel's payments over several workers. A shared accept
socket left 7 workers at the ceiling of their core and 2 under 10%. The AOF rewrite
child burned the other half of Redis's core on the keyspace earlier runs left
behind, which also moved `EVALSHA` from 36 to 72 µs. One ceiling was a constant in a
shell script. None of them was the price of the design: fixing them lowered what a
payment cost the box without changing what the scheme asks for.

The two that remain are the price of the design, and each needs a different kind of
change.

**The serving thread of `redis-vendor`.** No core buys anything here: one thread
executes every command. Two paths out. Cut what a payment writes, which section 1
prices directly — the modes rank by their `SET` and `ZADD` count, so the scheme with
fewer writes moves first. Or give the problem more than one thread, which means more
than one instance: `infrastructure/database.py` holds a single `database_url` and all
twelve workers connect to it, so sharding is a code change that routes by key, not an
environment variable.

**The fixed cost of an HTTP request in the vendor.** It binds `signature` now and
forms the floor for the other four the moment Redis leaves the front. Raising the
interpreter attacks the widest frames without touching the protocol, and the pin at
`<3.10.0` is the first thing to check there. Amortizing the fixed cost — more than
one payment per request — attacks the whole layer above the handler, which is 544 to
795 µs of every payment.

---

## 5. What this means for comparing the schemes

The comparison the benchmark exists to make is between payment schemes, and the
schemes account for a fraction of what the box spends. `signature` spends 290 µs of
1462 on crypto. The four paytree and payword modes spend 16 to 49 µs of 650 to 1127
on it, and 193 to 301 µs in Redis. Everything else belongs to the harness — the
framework above the handler, the interpreter inside it.

Two consequences for how results get reported. TPS states the size of the box as
much as the cost of the scheme, so CPU per payment is the figure that carries across
machines, and it is what sections 1 and 3 report. And the ranking survives the
overhead while the absolute numbers do not: the four paytree and payword modes order
themselves by the writes their script performs, which belongs to the scheme, whereas
what each of them costs is set by Python and Starlette. A gap between two schemes
narrower than that overhead has no reading yet.

---

## 6. What to trust when measuring this

Three readings agreed on every figure that decided something here: `mpstat` per
core, the in-container probe over `/proc`, and cadvisor through Prometheus. One
disagreed — `docker stats --no-stream` reported the vendor at 6.6% of one core during
the runs in section 1, while the other three put it above 11 cores.

A container total hides the distribution inside it, and twice in this investigation
the container sat at its limit while the process doing the work did not. Any ceiling
diagnosed from a cgroup total needs the split behind it: per worker, per command,
per core.

In `commandstats`, a command called from Lua is counted on its own *and* inside the
`EVALSHA` that called it, so the two cannot be added.

Reproduction commands for all of the above live in section 11 of
[worker-affinity-and-saturation.md](worker-affinity-and-saturation.md). The two that
produce the tables here:

```sh
poetry run python scripts/probe-saturation.py 12          # one plateau, attributed
poetry run python -m bench_plotter.saturation tps_saturation_timing.json
```

The second writes the expected-vs-real chart, the ceiling per mode, the macro/micro
CPU table, and one flame graph per mode into `plots/<timestamp>/`.
