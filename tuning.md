# Host tuning for consistent benchmarks

The benchmark results carry a load-dependent artifact: p50 latency *drops* as
TPS rises, and mCPU per payment shrinks the same way. Both are backwards. A real
queueing system gets slower and more expensive under load, not faster and
cheaper, so these curves are describing the operating system's idle behavior
rather than the payment protocols we set out to measure. This document traces
that behavior to its source and lays out the tuning that removes it. The target
throughout is determinism — a platform that costs the same per payment at 16 TPS
as it does at 256 TPS — because only then do paytree, payword, and signature
compare on equal footing.

## Strategy summary

| Strategy | Why it works | Requires reboot? | Survives reboot? | Affects other users? | Pros | Cons |
|---|---|---|---|---|---|---|
| **Disable C2 idle state** | Stops the 800 µs deep-sleep wake-up that is charged to each low-TPS request | No | No (unless scripted) | No — scoped to the hot cores | Kills the latency slope; instant revert; no reboot; scoped to the hot cores | Those cores draw more idle power and run warmer |
| **Performance governor** | Keeps a core from clocking down under light load | No | No (unless scripted) | Yes — set on every core | Removes the low-TPS downclock penalty; costs nothing to keep; no reboot | Reverting to `schedutil` hands the variance back — otherwise none |
| **Turn off boost** | Pins the clock near the 2.5 GHz base so it stops floating with temperature and core count | No | No (unless scripted) | Yes — global toggle, all cores | Fixed clock, directly comparable runs; instant revert; no reboot | Peak single-core speed ~30% lower, so absolute numbers drop |
| **Pin IRQs off hot cores** | Moves interrupt handling onto the housekeeping cores | No | No (unless scripted) | Yes — reroutes interrupts machine-wide | Removes interrupt jitter; cheap; no reboot | Concentrates IRQ load on `0-5`; some IRQs reset on driver reload |
| **Isolate cores** (`isolcpus`/`nohz_full`/`rcu_nocbs`/`max_cstate`/`nmi_watchdog`/THP) | Removes the kernel timer tick, RCU, kthreads, and NMI from the hot cores | Yes | Yes (GRUB) | Yes — cores leave the shared pool | Most thorough jitter removal short of `nosmt`; persists by construction | Needs a reboot; housekeeping cores absorb the offloaded work; a bad core list is caught only after reboot |
| **Disable SMT** (`nosmt`) | Removes the sibling threads that share execution units | Yes | Yes (GRUB) | Yes — halves CPUs for everyone | Guarantees a core's throughput is its own | Halves logical CPUs, 48 → 24 |
| **`idle=poll`** | Keeps cores awake so C-state exit latency is zero | Yes | Yes (GRUB) | Yes — systemwide idle behavior | Lowest, most uniform wake-up latency | Constant power and heat; redundant once C2 is disabled |
| **`mitigations=off`** | Drops speculative-execution workarounds and their syscall overhead | Yes | Yes (GRUB) | Yes — systemwide security posture | Less per-syscall overhead and variance | Disables Spectre/Meltdown protection; dedicated bench box only |

The sections below expand each row, in the order you should reach for them:
begin with the single write that fixes the slope and move down only if variance
survives. A running caveat applies to all of them — nothing here outlasts a
reboot on its own, which the [persistence](#making-it-survive-a-reboot) section
handles once.

## The benchmark host

Everything below is specific to the box the sweep runs on: an AMD EPYC 9224
(Zen 4), 24 cores and 48 threads on a single socket, presented as one NUMA node.
Its cores are grouped into L3/CCX clusters of six — `6-11`, `12-17`, `18-23`,
and so on — and each physical core exposes an SMT sibling at `N+24`. The
The `docker-compose.yml` pinning gives the vendor as much of that machine as it
can take without contending with anything that would distort the measurement: it
holds `1-10,19-20`, twelve physical cores, one per uvicorn worker. What is left out
is deliberate — `11` and `18` for its own Redis, `12-14,21` for the load generator,
`16` and `17` for the issuer and its Redis, `22-23` for the monitoring stack, and
`0` plus `15` for housekeeping and interrupts. Those exclusions are the reason the vendor is
pinned at all rather than left unconstrained: `cpuset` cannot reserve a core, so
an unpinned vendor would spread straight onto them, and time stolen from a
sequential client loop reads back as vendor latency that no plot can attribute
correctly. The split between the two sides follows one rule — the vendor gets at
least three cores per client core, here twelve against four — so the ceiling a sweep
finds belongs to the server and not to the generator. The kernel is 6.8, which
matters later because it ships the EEVDF scheduler in place of CFS.

## What the plots are actually showing

Three symptoms travel together. The latency curve
(`latency_p50_vs_tps.png`) slopes downward as load climbs, the cost curve
(`cpu_seconds_per_payment_vs_tps.png`) does the same, and the absolute numbers
wander between runs even though the cores are pinned. They are one phenomenon
seen from three angles: an idle core is slow to wake up and slow to return to
full speed, and it spends far more of its time idle at low TPS than at high TPS.
At 16 TPS the machine is mostly waiting; at 256 TPS it is mostly working, and a
working core is a fast core.

## Why it happens

The dominant cause is the processor's idle states. On a service core they read:

```
state0: POLL   exit=0us
state1: C1     exit=1us
state2: C2     exit=800us
```

That last line is the whole story. At 16 TPS requests arrive roughly 62 ms
apart, which dwarfs any C-state residency target, so between essentially every
request the core sinks into C2 and then spends 800 microseconds climbing back
out when the next request lands. That exit latency is charged to the request
that woke the core. At 256 TPS the gaps close to about 4 ms, the core never
descends past a shallow state, and the penalty disappears — which accounts for
most of the 0.3-0.4 ms swing in the latency plot. The frequency governor has no
say here, because a governor only acts on a core that is running; C-states
belong to the core when it is idle, and that is exactly when the damage is done.

Frequency scaling stacks a second effect on top. The old `schedutil` governor
clocked the core down under light load, which we already corrected by moving to
`performance`. Boost, however, still floats the clock between the 2.5 GHz base
and roughly 3.7 GHz according to temperature and how many cores are busy, and it
does so even under the `performance` governor and even with `scaling_max_freq`
capped, because boost simply overrides the cap. A core coming out of idle also
has to ramp its frequency back up, so the same low-TPS request that pays the
C-state exit also runs its first microseconds slow.

Beneath those two, smaller sources of jitter remain. Docker's `cpuset` keeps our
processes from migrating, but it does nothing about the kernel's own work: the
periodic 1000 Hz timer tick, RCU callbacks, and assorted kthreads still land on
the "pinned" cores and nudge the timing. The SMT siblings at `N+24` share
execution units with the benchmark cores, so anything scheduled onto a sibling
quietly steals throughput. Interrupts do the same when they are left free to
target a hot core. And transparent huge pages invite `khugepaged` to compact
memory in the background, which surfaces as occasional latency spikes on the
Redis and database path.

## Strategies

The right discipline is one knob per sweep. Each strategy below is isolated on
purpose so that when a curve flattens, its cause is unambiguous; changing six
things at once buys a flat plot and no understanding. They are ordered roughly by
impact and by cost, from the single write that fixes the slope to the reboots
that reach deepest into the system.

### Disable the C2 idle state

C2 owns the latency slope, and it undoes itself with a single write per core.
Disabling it holds the hot cores in C1 at most, which they exit in a
microsecond, so a request never again pays the 800-microsecond wake-up.

```bash
for c in $(seq 1 23); do
  echo 1 | sudo tee /sys/devices/system/cpu/cpu$c/cpuidle/state2/disable
done
```

**Pros:** removes the dominant cause of the latency-vs-TPS slope; reverts with a
single `echo 0`; no reboot; scoped to just the benchmark cores.
**Cons:** those cores draw more idle power and run warmer, since they no longer
reach the deep sleep state.

### Keep the performance governor

The governor is what stops a core from clocking down under light load. It is
already set to `performance`, and it stays there — this is a fix, not a problem.

```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

**Pros:** eliminates load-based downclocking, a direct source of the low-TPS
penalty; no reboot; costs nothing to keep.
**Cons:** none worth the name for a benchmark box; reverting to `schedutil` would
hand the variance straight back.

### Turn off turbo boost

With C2 gone, boost is the remaining reason the clock still moves. Turning it off
pins the frequency near the 2.5 GHz base so it never drifts with temperature or
core count.

```bash
echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost
```

**Pros:** a fixed clock makes runs directly comparable; no reboot; instantly
reversible.
**Cons:** peak single-core speed falls by roughly 30%, so absolute latency and
TPS land lower. The comparison between paytree, payword, and signature — the
point of the benchmark — is unaffected.

### Pin interrupts away from the hot cores

Steering every IRQ onto the housekeeping cores keeps interrupt handling off the
cores running the services. Growing the vendor to ten cores shrank that
housekeeping set to two, `0` and `15`, which is why core `0` is excluded from the
vendor in the first place — the boot CPU is the one core the kernel is least
willing to give up, so it is the natural place to send the interrupts.

```bash
# per-IRQ files take a core list; default_smp_affinity takes a hex mask
# cores 0 and 15 = bit 0 | bit 15 = 8001
for irq in /proc/irq/*/smp_affinity_list; do echo 0,15 | sudo tee "$irq" 2>/dev/null; done
echo 8001 | sudo tee /proc/irq/default_smp_affinity
```

Two cores is thin for a machine-wide IRQ load, but less thin than it looks for
this benchmark: the traffic never crosses a physical NIC. Client, vendor, and
issuer talk over a Docker bridge, where packet processing happens in softirq
context on the CPU that queued the packet rather than through a device interrupt,
and `smp_affinity` has no say over that. What this step actually removes is the
unrelated device and timer interrupt noise, which two cores absorb comfortably.

**Pros:** removes interrupt jitter from the vendor and client cores; no reboot;
cheap.
**Cons:** concentrates all device interrupt load on `0` and `15`, so those two
must stay out of every service `cpuset`; some IRQs pin back to their default on
device or driver reload; it does nothing for the bridge softirq work, which stays
on the sending core by construction.

### Isolate the cores at the kernel level

This is the deep fix for scheduler, timer, and RCU jitter, and it makes the C2
disable permanent. Added to `GRUB_CMDLINE_LINUX` in `/etc/default/grub` and
applied with `update-grub`, it pulls the benchmark cores out of the general
scheduler, silences their 1000 Hz timer tick, offloads their RCU callbacks onto
the housekeeping cores at `0-5` and `24-29`, caps idle at C1, drops the per-core
NMI watchdog interrupt, and turns off transparent huge pages. It names the SMT
siblings at `+24` alongside every core it isolates.

```
isolcpus=6-23,30-47 nohz_full=6-23,30-47 rcu_nocbs=6-23,30-47 processor.max_cstate=1 nmi_watchdog=0 transparent_hugepage=never
```

**Pros:** the most thorough jitter removal available short of disabling SMT;
covers timer, RCU, kthread, NMI, C-state, and THP noise in one line; persists
across reboots by construction.
**Cons:** requires a reboot; the isolated cores leave the general pool, and their
RCU and timer work piles onto the housekeeping cores, which must be sized to
absorb it; a mistake in the core list is only caught after the reboot.

The list above predates the current pinning. What it should isolate now is the
vendor and client cores together with their SMT siblings, leaving the housekeeping
pair, the datastores, and the monitoring cores in the general pool to absorb the
offloaded RCU and timer work:

```
isolcpus=1-14,25-38 nohz_full=1-14,25-38 rcu_nocbs=1-14,25-38 processor.max_cstate=1 nmi_watchdog=0 transparent_hugepage=never
```

Core `0` stays out on purpose. It is the boot CPU, several kernel facilities
assume it is schedulable, and it is where the interrupt step above sends the IRQs.

One trap comes with this step rather than from it. `isolcpus` makes an *unpinned*
container worse off than a pinned one: the scheduler will not balance onto
isolated cores, so a service with no `cpuset` is confined to the housekeeping
cores instead of running anywhere. Dropping the vendor's `cpuset` to "give it
every core" would, on an isolated boot, silently hand it the fewest — and nothing
in the logs would say so.

### Disable SMT

Booting with `nosmt` (or `echo off > /sys/devices/system/cpu/smt/control`)
removes the sibling threads entirely, so nothing shares execution units with a
benchmark core.

**Pros:** erases SMT contention outright; the cleanest guarantee that a core's
throughput is its own.
**Cons:** halves the logical CPU count from 48 to 24, shrinking the pool for
everything else on the box.

### Poll instead of idling

`idle=poll` on the kernel command line keeps cores permanently awake, driving
C-state exit latency to zero.

**Pros:** the lowest and most uniform wake-up latency possible.
**Cons:** the cores run flat out even while idle, spending continuous power and
heat; overkill once C2 is already disabled.

### Drop CPU mitigations

`mitigations=off` strips the speculative-execution workarounds and the syscall
overhead they carry.

**Pros:** removes a source of per-syscall overhead and its run-to-run variance.
**Cons:** disables Spectre/Meltdown-class protections, so it belongs only on a
dedicated, isolated bench box and never on anything exposed.

## The Docker layer

Every host knob above only matters on the exact cores the containers run on, and
`docker-compose.yml` is what decides that. The two layers are complementary:
Docker gives *placement*, the host tuning gives *exclusivity and idle behavior*
on the same cores. The pinning is already correct — `cpuset` puts the vendor's twelve
workers on `1-10,19-20` beside its Redis on `11` and `18`, the load generator's four
processes on `12-14,21`, the issuer on `16` beside its Redis on `17`, and the
monitoring stack out on `22-23`. Every command in this document targets those same core numbers for
exactly that reason. There are, however, four things the compose file cannot do
on its own.

The first is exclusivity. `cpuset` keeps *that container* from wandering off its
cores, but it does nothing to stop the kernel, another container, or a stray
process from also scheduling onto them. Only `isolcpus` genuinely reserves a
core, which is why the Docker pinning and the kernel-level isolation are two
halves of the same fix rather than alternatives.

The second is one process per core. A `cpuset` of ten cores holding ten uvicorn
workers still lets the scheduler shuffle those workers among the ten, and a worker
that lands on a different core arrives with a cold L3. Affinity is per process, so
this one is settled inside the container: `VENDOR_PIN_WORKERS_TO_CORES` has each
worker claim a core of the `cpuset` for its lifetime as it starts up, and
`CLIENT_PIN_PROCESSES_TO_CORES` does the same for the generator's processes. Claims
are exclusive, so a `cpuset` smaller than the worker count leaves the surplus
workers unpinned rather than doubled up — the startup log says which core each one
took, or that it got none.

Pinning only decides *where* a worker runs; work still has to reach it, and that
is the other half of the same problem. Uvicorn's own multi-worker mode has every
worker accept from one shared listening socket and lets the kernel pick, which is
not the round-robin one might assume: measured with 40 client connections over ten
workers, the spread was 1 to 7 connections per worker, the loaded ones sat at
84-91% of their single core, two sat below 10%, and the vendor plateaued at 5400
TPS while looking half idle at 5.5 of 10 cores. So the vendor instead runs one
single-worker server per port, `VENDOR_API_PORT` upward, one listening socket
each, and the load generator dials port `base + (client index % CLIENT_VENDOR_PORT_COUNT)`.
Because a keep-alive connection is served end to end by the worker that accepted
it, choosing the port chooses the worker: the same 40 clients then landed exactly
4 per worker, all ten between 81% and 91%, for 8.6 of 10 cores and 6800 TPS. Keep
`CLIENT_VENDOR_PORT_COUNT` equal to `VENDOR_API_WORKERS` and the virtual-client
count a multiple of it, or the arithmetic reintroduces the imbalance it removes.
`scripts/probe-worker-connections.py` prints the per-worker connection and CPU
split that cadvisor's container total hides.

The third is the SMT sibling. Pinning to hardware thread 6 leaves its sibling
30 — the other thread on the same physical core, sharing its execution units —
free for anything to land on, and whatever lands there steals throughput from
the vendor unpredictably. Docker has no way to express "reserve the sibling
too," so this is handled at the host level by naming the `+24` siblings in the
C-state and isolation steps, or by disabling SMT outright.

The fourth is Redis persistence. Both Redis containers run `--appendonly yes`, so
the AOF `fsync` (default `everysec`) is a periodic background disk write sitting
on the critical path — a source of occasional latency spikes unrelated to the
payment logic. If durability is not part of what the benchmark measures,
`--save "" --appendonly no` removes it entirely; if it is, `--appendfsync no`
lets the OS flush on its own schedule and at least takes the `fsync` off the
timed path.

Keeping the AOF costs a core, which is why `redis-vendor` holds two. The rewrite
is done by a forked child, and a fork inherits the `cpuset`: on a single core it
competed head to head with the one thread that serves payments. Measured under
`paytree_child_pair`, the core was pegged at 100% while `redis-server` itself
accounted for only half of it — two `redis-server` processes sat on that core, the
second appearing only for the duration of the run. Serving a payment costs Redis
about 105 µs of CPU (two round-trips: one `MGET`, then one `EVALSHA` whose 72 µs
covers all the writes, of which the `SET`/`ZADD`/`GET` calls are only ~23 µs), so
the ceiling that reads back as "Redis is saturated" was mostly rewrite work. The
second core comes from the monitoring block rather than from the vendor or the
generator, and landing in another L3 is a feature: the rewrite streams the whole
dataset and would otherwise evict the serving thread's cache. The other half of
this is not a tuning knob at all — nothing deletes keys after a run, so the sweep
flushes both datastores before each one, otherwise the rewrite each mode pays for
is sized by every mode that ran before it.

Two smaller notes: there are no `mem_limit`s, which is fine here — 257 GB free on
a single NUMA node means no memory pressure and no cross-node variance to worry
about — and the containers inherit host swap, which is harmless as long as the
box keeps swap off or untouched during a sweep.

## Making it survive a reboot

This is a caveat that rides along with every strategy above, not a strategy of
its own: none of the knobs outlast a reboot unless you make them, and the two
classes of setting persist differently. Anything on the kernel command line —
the isolation flags, `max_cstate`, `nosmt`, the THP mode — lives in GRUB.
The sysfs values are handled by `sysfsutils`, whose config paths are written
relative to `/sys`:

```bash
sudo apt update && sudo apt install sysfsutils -y
# /etc/sysfs.conf
devices/system/cpu/cpufreq/boost = 0
kernel/mm/transparent_hugepage/enabled = never
```

The per-CPU settings that `sysfsutils` cannot express cleanly — the governor and
the per-core C-state disable — belong in a small `scripts/host-tune.sh` invoked
at boot or immediately before a sweep.

## Confirming the fix

The change is easiest to see in idle residency and clock speed, sampled through
a low-TPS run:

```bash
sudo turbostat --interval 1 --show Core,CPU,Busy%,Bzy_MHz,CPU%c1,CPU%c2 -- sleep 30
```

Beforehand, 16 TPS shows heavy `CPU%c2` residency and a `Bzy_MHz` that bounces
around. With C2 and boost gone, `%c2` collapses to nearly zero and `Bzy_MHz`
holds steady. Re-running the sweep then tells the real story: p50 latency and
mCPU per payment go flat, or tip gently upward, across TPS. That flat line is
the proof that the original slope belonged to the operating system and not to
the payment logic.

## A note on the scheduler slice

The familiar `sched_min_granularity_ns` knob from the CFS era is gone on 6.8,
which runs EEVDF instead. Its successor is `base_slice_ns`:

```bash
sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null
cat /sys/kernel/debug/sched/base_slice_ns
```

Widening it lets CPU-bound tasks run longer before preemption, trimming context
switches and steadying CPU accounting. It is a second-order adjustment, though:
once `isolcpus` and `nohz_full` clear the hot cores of competing work, there is
nothing left to preempt against, and the slice stops mattering. Reading or
writing it needs `CONFIG_SCHED_DEBUG` and a mounted debugfs.

## In short

The `performance` governor was the right call and stays. The
latency-drops-with-TPS artifact comes from the 800-microsecond C2 exit latency,
which no governor can reach. Disabling C2 on the hot cores is the highest-impact
move and the first one to make; boost-off, isolation, and the rest follow only
if variance survives, and only one at a time.
