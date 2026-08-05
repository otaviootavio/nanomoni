"""Tests for per-process core pinning.

The property that matters is exclusivity: if two vendor workers claimed the same
core the benchmark would silently run with one core idle and two workers sharing
another, which looks like a slow protocol rather than a misconfiguration.
"""

from __future__ import annotations

import os
from multiprocessing import get_context
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Barrier
from typing import Any, Iterable, List, Optional, Set, Tuple

import pytest

from nanomoni.cpu_affinity import pin_to_own_core


pytestmark = pytest.mark.skipif(
    not hasattr(os, "sched_setaffinity"),
    reason="CPU affinity is Linux-only",
)


def _claim(
    lock_dir: str, allowed: Set[int], results: "Queue[Any]", ready: Barrier
) -> None:
    """Claim a core out of ``allowed`` and hold it until every sibling has tried."""
    os.sched_setaffinity(0, allowed)
    core = pin_to_own_core(label="test", lock_dir=lock_dir)
    results.put((core, sorted(os.sched_getaffinity(0))))
    ready.wait(timeout=30)


def _run_claimers(
    lock_dir: str, allowed: Set[int], count: int
) -> List[Tuple[Optional[int], List[int]]]:
    ctx = get_context("fork")
    results: "Queue[Any]" = ctx.Queue()
    ready = ctx.Barrier(count)
    procs = [
        ctx.Process(target=_claim, args=(lock_dir, allowed, results, ready))
        for _ in range(count)
    ]
    for proc in procs:
        proc.start()
    # Drained before joining: a full pipe would deadlock a child inside join().
    collected = [results.get(timeout=30) for _ in procs]
    for proc in procs:
        proc.join(timeout=30)
    return collected


def _sorted_claimed(claims: Iterable[Tuple[Optional[int], List[int]]]) -> List[int]:
    """Drop unclaimed slots so a missing core shows up as a length mismatch."""
    return sorted(core for core, _ in claims if core is not None)


def _available_cores(count: int) -> Set[int]:
    cores = sorted(os.sched_getaffinity(0))
    if len(cores) < count:
        pytest.skip(f"needs {count} available cores, host offers {len(cores)}")
    return set(cores[:count])


def test_each_process_claims_a_distinct_core(tmp_path: Any) -> None:
    allowed = _available_cores(3)

    claims = _run_claimers(str(tmp_path), allowed, len(allowed))

    assert _sorted_claimed(claims) == sorted(allowed)
    for core, affinity in claims:
        assert affinity == [core]


def test_extra_processes_keep_their_inherited_affinity(tmp_path: Any) -> None:
    allowed = _available_cores(2)

    claims = _run_claimers(str(tmp_path), allowed, len(allowed) + 1)

    unpinned = [affinity for core, affinity in claims if core is None]
    assert len(unpinned) == 1
    assert unpinned[0] == sorted(allowed)


def test_a_released_core_is_reclaimed(tmp_path: Any) -> None:
    allowed = _available_cores(2)

    first = _run_claimers(str(tmp_path), allowed, len(allowed))
    second = _run_claimers(str(tmp_path), allowed, len(allowed))

    assert _sorted_claimed(first) == sorted(allowed)
    assert _sorted_claimed(second) == sorted(allowed)
