"""Assert the number of distinct node-store entries first-opt vs. second-opt
leave behind for the same sequence of real payments.

Uses ``MerkleNodeRepositoryImpl.count_nodes`` (the same ``merkle_node_index``
ZSET ``delete()`` already relies on) against a fakeredis-backed store -- no
Redis/Docker required. ``tests/integration/test_paytree_node_storage_real_redis.py``
runs this exact scenario against real Redis and asserts the same numbers, so
the counts here aren't just an artifact of the mock.

Expected counts were derived by running the scenario once and reading off
the actual result (see that PR/commit), not hand-computed -- the LCA-pruning
arithmetic is easy to get wrong by hand (learned the hard way earlier in
this codebase's history). Full tree for MAX_STEPS=7 (depth 3, 8 leaves) has
2^4 - 1 = 15 possible node keys.
"""

from __future__ import annotations

import pytest

from nanomoni.infrastructure.scripts import VENDOR_SCRIPTS
from tests.fixtures.in_memory_storage import InMemoryKeyValueStore
from tests.fixtures.paytree_node_storage_scenarios import run_node_storage_scenario

INDICES = [1, 2, 3, 4, 5, 6, 7]
SEED = b"node-storage-count-test"

# Running count of distinct node keys after each payment i=1..7.
EXPECTED_FIRST_OPT = [5, 7, 7, 11, 11, 13, 13]
EXPECTED_SECOND_OPT = [7, 9, 9, 13, 13, 15, 15]

FULL_TREE_SIZE = 15


@pytest.mark.asyncio
async def test_first_opt_node_count_stays_sparse() -> None:
    """First-opt (P only) never recovers the 2 ancestor nodes that no
    payment in this sequence ever needs as a sibling -- it plateaus at
    13/15, short of the full tree."""
    store = InMemoryKeyValueStore()
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)

    counts = await run_node_storage_scenario(
        store, "first-opt-node-count", second_opt=False, indices=INDICES, seed=SEED
    )

    assert counts == EXPECTED_FIRST_OPT
    assert counts[-1] < FULL_TREE_SIZE


@pytest.mark.asyncio
async def test_second_opt_node_count_reaches_full_tree() -> None:
    """Second-opt (P + Q) reuses every hash computed while verifying, so the
    same 7 payments reconstruct the complete tree: 15/15."""
    store = InMemoryKeyValueStore()
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)

    counts = await run_node_storage_scenario(
        store, "second-opt-node-count", second_opt=True, indices=INDICES, seed=SEED
    )

    assert counts == EXPECTED_SECOND_OPT
    assert counts[-1] == FULL_TREE_SIZE


@pytest.mark.asyncio
async def test_second_opt_stores_strictly_more_nodes_than_first_opt() -> None:
    """Same payments, same tree, same order -- second-opt's P+Q write always
    dominates first-opt's P-only write, node for node."""
    first_opt_store = InMemoryKeyValueStore()
    second_opt_store = InMemoryKeyValueStore()
    for store in (first_opt_store, second_opt_store):
        for name, script in VENDOR_SCRIPTS.items():
            await store.register_script(name, script)

    first_opt_counts = await run_node_storage_scenario(
        first_opt_store,
        "first-opt-vs-second-opt-a",
        second_opt=False,
        indices=INDICES,
        seed=SEED,
    )
    second_opt_counts = await run_node_storage_scenario(
        second_opt_store,
        "first-opt-vs-second-opt-b",
        second_opt=True,
        indices=INDICES,
        seed=SEED,
    )

    assert all(s >= f for f, s in zip(first_opt_counts, second_opt_counts)), (
        "second-opt must never store fewer distinct nodes than first-opt at any step"
    )
    assert second_opt_counts[-1] > first_opt_counts[-1]
