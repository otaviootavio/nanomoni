"""Tests for the fixed-rate payment pacer's bias/spin compensation and resync.

These exercise the real clock rather than mocking ``sleep``/``perf_counter``:
the bug this pacer fixes is specifically about how the event loop's timer
quantizes real sleep calls (see ``pacing.py``'s module docstring), so a mock
that assumes a single, linear relationship between requested and actual sleep
duration would validate the wrong model and miss exactly the regression this
module exists to prevent.
"""

from __future__ import annotations

import asyncio
from time import perf_counter

import pytest

from nanomoni.client.pacing import Pacer


def _busy_wait(seconds: float) -> None:
    """Block the current task for ``seconds`` without touching the event loop.

    Stand-in for the CPU-bound part of a payment (proof generation) plus a
    fast request/response, without depending on real network I/O.
    """
    until = perf_counter() + seconds
    while perf_counter() < until:
        pass


@pytest.mark.asyncio
async def test_zero_delay_never_waits() -> None:
    """Unpaced (max-throughput) runs must return immediately for every slot."""
    pacer = Pacer(0.0)
    start = perf_counter()
    for n in range(50):
        await pacer.wait_for_slot(n)
    assert perf_counter() - start < 0.01


@pytest.mark.asyncio
async def test_first_slot_needs_no_wait_when_already_due() -> None:
    """Slot 0's target is the construction time, so it's already due."""
    pacer = Pacer(0.05)
    start = perf_counter()
    await pacer.wait_for_slot(0)
    assert perf_counter() - start < 0.01


@pytest.mark.asyncio
async def test_recovers_a_multi_slot_stall_under_the_absolute_floor() -> None:
    """A stall bigger than one slot but comfortably under the absolute floor
    (ordinary jitter -- a GC pause, a slow request -- not a genuine hang)
    must be recovered via a bounded catch-up, not permanently forgiven the
    way a stall past the floor is (see the next test)."""
    target_tps = 500
    delay = 1.0 / target_tps
    pacer = Pacer(delay)
    n_before_stall = 20
    start = perf_counter()
    for i in range(n_before_stall):
        await pacer.wait_for_slot(i)

    await asyncio.sleep(0.02)  # one ~20ms stall (10 slots), under the 50ms floor

    n_after_stall = 200
    for i in range(n_before_stall, n_before_stall + n_after_stall):
        await pacer.wait_for_slot(i)
        _busy_wait(0.0006)

    total = n_before_stall + n_after_stall
    achieved_tps = total / (perf_counter() - start)
    # A pacer that instead forgave the stall (the pre-fix threshold) would
    # land close to 478 TPS here (target minus the unrecovered 20ms over this
    # test's ~0.44s ideal duration) -- comfortably outside this tolerance.
    assert achieved_tps == pytest.approx(target_tps, rel=0.03)


@pytest.mark.asyncio
async def test_large_stall_resyncs_to_one_delay_not_zero_or_a_burst() -> None:
    """A miss bigger than one slot must reset the anchor to "now", so the next
    slot waits one full delay rather than firing immediately (which a naive
    reset to "now" without re-anchoring would do) or bursting through several
    slots' worth of accumulated backlog at once."""
    delay = 0.02
    pacer = Pacer(delay)
    await asyncio.sleep(delay * 3)  # simulate a stall well past slot 0's schedule
    await pacer.wait_for_slot(0)  # already due -- returns immediately

    start = perf_counter()
    await pacer.wait_for_slot(1)
    elapsed = perf_counter() - start
    assert delay * 0.5 < elapsed < delay * 1.5


@pytest.mark.asyncio
async def test_hits_target_rate_despite_sub_millisecond_timer_granularity() -> None:
    """End-to-end regression for the actual bug: at a target rate whose slot
    is comparable to the event loop's timer floor (~1ms), the pacer must
    still deliver close to the requested rate, not the ~97% a plain
    ``sleep(remaining)`` settles at (see this module's docstring)."""
    target_tps = 500
    n = 300
    pacer = Pacer(1.0 / target_tps)
    start = perf_counter()
    for i in range(n):
        await pacer.wait_for_slot(i)
        _busy_wait(0.0006)  # stand-in for a fast payment round-trip
    achieved_tps = n / (perf_counter() - start)
    assert achieved_tps == pytest.approx(target_tps, rel=0.03)


@pytest.mark.asyncio
async def test_hits_target_rate_at_a_rate_below_the_timer_floor() -> None:
    """At a rate well below the timer floor, the compensated-sleep branch
    (rarely reaching the spin tail) should already be enough on its own."""
    target_tps = 50
    n = 60
    pacer = Pacer(1.0 / target_tps)
    start = perf_counter()
    for i in range(n):
        await pacer.wait_for_slot(i)
        _busy_wait(0.001)
    achieved_tps = n / (perf_counter() - start)
    assert achieved_tps == pytest.approx(target_tps, rel=0.03)
