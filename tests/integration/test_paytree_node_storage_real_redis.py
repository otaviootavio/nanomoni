"""Same node-count scenario as tests/use_cases/test_paytree_node_storage.py,
run against real Redis instead of fakeredis.

Requires only ``redis-vendor`` reachable at localhost:6379 (db 15, isolated
from the app's db 0) -- not the full docker compose stack, and not gated by
the e2e-services hook (that hook only fires on commands mentioning ``e2e``).
Uses the ``redis_store``/``redis_db_client`` fixtures already defined in
``tests/conftest.py``; those fixtures ``pytest.skip`` this test automatically
if Redis isn't reachable, rather than failing.

The point of duplicating the scenario here (instead of trusting the
fakeredis run alone) is that ``InMemoryKeyValueStore`` executes the exact
same Lua scripts through fakeredis's embedded interpreter -- real Redis is
the thing that actually backs production, so this is the check that the
sparse (first-opt) vs. dense (second-opt) node counts aren't an artifact of
the mock.

Run explicitly with: poetry run pytest -m integration tests/integration
"""

from __future__ import annotations

import pytest

from nanomoni.infrastructure.scripts import VENDOR_SCRIPTS
from nanomoni.infrastructure.storage import RedisKeyValueStore
from tests.fixtures.paytree_node_storage_scenarios import run_node_storage_scenario

INDICES = [1, 2, 3, 4, 5, 6, 7]
SEED = b"node-storage-count-test"

EXPECTED_FIRST_OPT = [5, 7, 7, 11, 11, 13, 13]
EXPECTED_SECOND_OPT = [7, 9, 9, 13, 13, 15, 15]

FULL_TREE_SIZE = 15


async def _register_scripts(store: RedisKeyValueStore) -> None:
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_first_opt_node_count_on_real_redis(
    redis_store: RedisKeyValueStore,
) -> None:
    await _register_scripts(redis_store)

    counts = await run_node_storage_scenario(
        redis_store,
        "first-opt-node-count-real-redis",
        second_opt=False,
        indices=INDICES,
        seed=SEED,
    )

    assert counts == EXPECTED_FIRST_OPT
    assert counts[-1] < FULL_TREE_SIZE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_second_opt_node_count_on_real_redis(
    redis_store: RedisKeyValueStore,
) -> None:
    await _register_scripts(redis_store)

    counts = await run_node_storage_scenario(
        redis_store,
        "second-opt-node-count-real-redis",
        second_opt=True,
        indices=INDICES,
        seed=SEED,
    )

    assert counts == EXPECTED_SECOND_OPT
    assert counts[-1] == FULL_TREE_SIZE
