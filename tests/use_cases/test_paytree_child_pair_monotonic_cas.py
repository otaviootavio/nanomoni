"""Regression-style coverage: child-pair PayTree save enforces an atomic monotonic CAS.

Child-pair payments reuse the exact same `save_nodes_and_payment` atomic
save as first-opt (see test_paytree_first_opt_monotonic_cas.py) — node_updates
is just an opaque str->str dict, so no scheme-specific Lua changes were
needed. This test locks in that the CAS semantics (reject stale/non-increasing
k, reject k beyond max_k, register new channels in the open/closed indexes)
also hold when node keys are child-pair-style (`str(k)`).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import pytest

from nanomoni.domain.shared.proof_reference import PaymentScheme
from nanomoni.domain.vendor.entities import PaymentChannel, PaymentState
from nanomoni.infrastructure.scripts import VENDOR_SCRIPTS
from nanomoni.infrastructure.vendor.merkle_node_repository_impl import (
    MerkleNodeRepositoryImpl,
)
from tests.fixtures.in_memory_storage import InMemoryKeyValueStore


async def _new_repo() -> tuple[InMemoryKeyValueStore, MerkleNodeRepositoryImpl]:
    store = InMemoryKeyValueStore()
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)
    return store, MerkleNodeRepositoryImpl(store)


def _make_channel(
    channel_id: str, *, max_steps: int, last_ref: Optional[int]
) -> PaymentChannel:
    return PaymentChannel(
        channel_id=channel_id,
        client_public_key_der_b64="client",
        vendor_public_key_der_b64="vendor",
        salt_b64="salt",
        amount=10_000,
        balance=0,
        is_closed=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        commitment="root",
        scheme=PaymentScheme.PAYTREE_CHILD_PAIR,
        max_steps=max_steps,
        unit_value=1,
        last_proof_reference=last_ref,
    )


def _make_state(channel_id: str, k: int) -> PaymentState:
    return PaymentState(
        channel_id=channel_id,
        proof_reference=k,
        cumulative_owed=k,
        proof_fingerprint=f"left-{k}:right-{k}",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


async def _save(
    repo: MerkleNodeRepositoryImpl, channel: PaymentChannel, k: int
) -> tuple[int, Optional[int]]:
    """Emulate the child-pair use case: node_updates keyed by str(2k)/str(2k+1)."""
    channel.last_proof_reference = k
    state = _make_state(channel.channel_id, k)
    node_updates = {str(2 * k): f"left-{k}", str(2 * k + 1): f"right-{k}"}
    return await repo.save_nodes_and_payment(
        channel_id=channel.channel_id,
        node_updates=node_updates,
        new_ref=k,
        channel_json=channel.model_dump_json(),
        state_json=state.model_dump_json(),
        proof_json="{}",
        is_closed=False,
        created_at_ts=channel.created_at.timestamp(),
    )


async def _stored_ref(store: InMemoryKeyValueStore, channel_id: str) -> Optional[int]:
    raw = await store.get(f"payment_state:{channel_id}")
    if not raw:
        return None
    return int(json.loads(raw)["proof_reference"])


@pytest.mark.asyncio
async def test_child_pair_save_rejects_stale_reference() -> None:
    store, repo = await _new_repo()

    status, ref = await _save(repo, _make_channel("c1", max_steps=7, last_ref=None), 3)
    assert (status, ref) == (1, 3)

    status, ref = await _save(repo, _make_channel("c1", max_steps=7, last_ref=3), 2)
    assert status == 0
    assert ref == 3
    assert await _stored_ref(store, "c1") == 3


@pytest.mark.asyncio
async def test_child_pair_save_prevents_reorder_double_write() -> None:
    store, repo = await _new_repo()

    await _save(repo, _make_channel("c1", max_steps=7, last_ref=None), 3)

    status_a, _ = await _save(repo, _make_channel("c1", max_steps=7, last_ref=3), 4)
    assert status_a == 1

    status_b, ref_b = await _save(repo, _make_channel("c1", max_steps=7, last_ref=3), 4)
    assert status_b == 0
    assert ref_b == 4
    assert await _stored_ref(store, "c1") == 4


@pytest.mark.asyncio
async def test_child_pair_save_rejects_reference_beyond_max_k() -> None:
    store, repo = await _new_repo()

    status, _ = await _save(repo, _make_channel("c1", max_steps=7, last_ref=None), 8)
    assert status == 3
    assert await _stored_ref(store, "c1") is None


@pytest.mark.asyncio
async def test_child_pair_save_registers_new_channel_in_indexes() -> None:
    store, repo = await _new_repo()

    status, _ = await _save(repo, _make_channel("c1", max_steps=7, last_ref=None), 1)
    assert status == 1

    assert "c1" in await store.zrevrange("payment_channels:all", 0, -1)
    assert "c1" in await store.zrevrange("payment_channels:open", 0, -1)
    assert "c1" not in await store.zrevrange("payment_channels:closed", 0, -1)


@pytest.mark.asyncio
async def test_child_pair_node_keys_are_plain_k_strings() -> None:
    """Node keys are `str(2k)`/`str(2k+1)` — no depth/level math required to store them."""
    store, repo = await _new_repo()
    await _save(repo, _make_channel("c1", max_steps=7, last_ref=None), 2)

    nodes = await repo.get_nodes("c1", ["4", "5"])
    assert nodes == {"4": "left-2", "5": "right-2"}
