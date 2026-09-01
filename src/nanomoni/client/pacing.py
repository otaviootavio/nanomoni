"""Fixed-rate pacing for benchmark payment loops.

``asyncio.sleep`` cannot return in less than the event loop's timer
resolution -- about 1ms on both the default ``SelectorEventLoop`` and uvloop,
since libuv's timer wheel is itself millisecond-granular. At target rates
faster than roughly 1000/s, the time remaining before a payment's scheduled
slot is well under that floor on almost every iteration, so a plain
``sleep(remaining)`` overshoots its slot systematically, not occasionally.
The fixed-rate schedule below only resyncs on a *large* miss (see the resync
branch), so this bias is never absorbed by that safety valve: it is present
at every target rate that exceeds the timer floor, and shows up as a client
that consistently delivers a few percent under its target TPS.

That overshoot is not a smooth, constant offset -- it is quantized into
discrete buckets (measured: a requested sleep under ~1ms actually takes
~1.07ms, one from ~1-2ms takes ~2.08ms, and so on). A ``requested`` duration
that sits right at one of those bucket boundaries flips between buckets on
tiny timing fluctuations, so a linear/EMA bias estimate (this module's first
approach) hunts around the boundary instead of converging: measured on the
real vendor at a 500/s target, it recovered only part of the shortfall
(~486 TPS -> ~487-494 TPS depending on run, still short of 500).

The bias estimate below is kept because it still saves CPU whenever
``remaining`` comfortably exceeds one bucket (mainly at lower target rates),
but the final ``_SPIN_MARGIN_S`` of any wait is never handed to
``asyncio.sleep`` at all -- it is spun out with ``await sleep(0)``, which
CPython special-cases to a bare event-loop-queue yield rather than a
timer-wheel entry, so it is not subject to the bucketing. The yield form
(not a blocking ``while`` loop) matters for correctness, not just style:
``CLIENT_VIRTUAL_CLIENTS`` fans several payment loops out over one event
loop via ``asyncio.gather``, and a loop with no ``await`` inside would
starve every other virtual client sharing it for the whole spin window.

With that bucketing fixed, measurement on the real vendor (instrumented run,
20000 payments @ 500/s) still landed short (~487 TPS), and the actual gap
turned out to be a third, independent effect: the resync branch below used
to fire on *any* miss bigger than one slot, and gave up that time completely
rather than trying to recover it. At a 2ms slot (500/s), real per-payment
cost (proof generation, the request, occasional GC pauses) spikes past one
slot often enough on its own -- 53 times over that run, discarding ~1.04s
total -- to fully account for the shortfall on its own, with no remaining
contribution from the timer bucketing above. ``_MAX_UNRECOVERED_STALL_S``
below is an absolute floor (not a slot multiple) so that stays true at any
target rate: it only gives up on stalls too big to be ordinary jitter,
letting the fixed-grid anchor recover everything smaller the same way it
already recovers sub-slot overshoots -- by making the next ``remaining``
smaller (or, for a multi-slot miss, a short and bounded catch-up of firing
a handful of payments with little to no gap, capped at whatever fits in
that floor).
"""

from __future__ import annotations

from asyncio import sleep
from time import perf_counter

# Smoothing factor for the sleep-bias estimate. Low enough that one transient
# stall (a slow request delaying the next call's measurement) doesn't swing
# the estimate, high enough that it adapts within a handful of payments.
_BIAS_SMOOTHING = 0.3

# Must exceed this loop's largest observed single-sleep-call bucket (measured
# ~1.07ms for sub-millisecond requests) with margin for scheduling jitter
# under load, so the compensated-sleep branch below is only ever used for a
# ``remaining`` comfortably clear of a bucket boundary; anything closer than
# this is spun out instead of risking another overshoot.
_SPIN_MARGIN_S = 0.0015

# Absolute floor (not a multiple of the slot size) for how far behind schedule
# is still worth trying to recover. Sized around the largest ordinary jitter
# observed on the real vendor (GC pauses, scheduling hiccups -- tens of ms,
# not slot-count-dependent), so it stays meaningful at high target rates
# (small slots) without changing behavior at low rates, where one slot is
# already bigger than this on its own.
_MAX_UNRECOVERED_STALL_S = 0.05


class Pacer:
    """Paces a sequence of awaited operations at a fixed inter-arrival delay.

    Anchors each slot to ``n * inter_payment_delay`` from a fixed start time
    (rather than sleeping ``inter_payment_delay`` in a loop), so a single
    overshoot doesn't drift every later slot -- only the resync path below
    ever moves the anchor.
    """

    def __init__(self, inter_payment_delay: float) -> None:
        self._delay = inter_payment_delay
        self._start = perf_counter()
        self._sleep_bias_s = 0.0

    async def wait_for_slot(self, n: int) -> None:
        """Block (best-effort) until payment ``n``'s scheduled slot arrives.

        No-op when constructed with a non-positive delay (unpaced/max-throughput
        runs), so callers don't need to guard every call themselves.
        """
        if self._delay <= 0:
            return

        target = self._start + n * self._delay
        now = perf_counter()
        if target - now <= -max(self._delay, _MAX_UNRECOVERED_STALL_S):
            # Fell behind by more than a slot AND more than the absolute floor
            # above (e.g. a genuinely stalled request, not just jitter) --
            # resync the schedule instead of trying to recover it, since a
            # miss this large would otherwise take an extended catch-up burst
            # well above the configured rate, contaminating steady-state
            # measurements. Smaller misses fall through to the loop below,
            # which recovers them via the anchor (a smaller/zero next wait,
            # or -- for a multi-slot miss under the floor -- a short, bounded
            # catch-up of a few back-to-back payments).
            self._start = now - n * self._delay
            return

        while True:
            now = perf_counter()
            remaining = target - now
            if remaining <= 0:
                return
            if remaining > _SPIN_MARGIN_S:
                requested = max(0.0, remaining - _SPIN_MARGIN_S - self._sleep_bias_s)
                slept_at = perf_counter()
                await sleep(requested)
                actual = perf_counter() - slept_at
                self._sleep_bias_s += _BIAS_SMOOTHING * (
                    (actual - requested) - self._sleep_bias_s
                )
            else:
                # Cooperative spin: yields to the event loop every iteration
                # (letting other virtual clients on this loop run) without
                # going through the timer wheel that causes the bucketing.
                await sleep(0)
