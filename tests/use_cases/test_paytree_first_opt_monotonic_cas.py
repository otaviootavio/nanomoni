"""Regression: first-opt PayTree save must enforce an atomic monotonic CAS.

Covers PR #68 review findings:

- H1: the first-opt save (`save_nodes_and_payment`) unconditionally overwrote the
  channel/state and always returned success, losing the atomic monotonic
  compare-and-swap the std/payword path enforces. Two concurrent requests reading
  the same previous reference could both write, moving `last_proof_reference`
  backwards (double-spend / reorder). The save must now reject any reference that
  is not strictly increasing versus the *stored* channel, and any reference beyond
  `max_steps`.
- M1: a brand-new first-opt channel was never registered in the
  `payment_channels:all` / `payment_channels:open` indexes, making it invisible to
  listing and cleanup.
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
        scheme=PaymentScheme.PAYTREE,
        max_steps=max_steps,
        unit_value=1,
        last_proof_reference=last_ref,
    )


def _make_state(channel_id: str, ref: int) -> PaymentState:
    return PaymentState(
        channel_id=channel_id,
        proof_reference=ref,
        cumulative_owed=ref,
        proof_fingerprint=f"leaf-{ref}",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


async def _save(
    repo: MerkleNodeRepositoryImpl, channel: PaymentChannel, ref: int
) -> tuple[int, Optional[int]]:
    """Emulate the use case: embed the new reference in the channel, then save."""
    channel.last_proof_reference = ref
    state = _make_state(channel.channel_id, ref)
    return await repo.save_nodes_and_payment(
        channel_id=channel.channel_id,
        node_updates={},
        new_ref=ref,
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
async def test_first_opt_save_rejects_stale_reference() -> None:
    store, repo = await _new_repo()

    # First payment i=5 succeeds and becomes the committed reference.
    status, ref = await _save(repo, _make_channel("c1", max_steps=128, last_ref=None), 5)
    assert (status, ref) == (1, 5)

    # A concurrent request that read prev=5 but arrives with a lower i must be
    # rejected atomically and must NOT overwrite the stored state.
    status, ref = await _save(repo, _make_channel("c1", max_steps=128, last_ref=5), 3)
    assert status == 0
    assert ref == 5
    assert await _stored_ref(store, "c1") == 5


@pytest.mark.asyncio
async def test_first_opt_save_prevents_reorder_double_write() -> None:
    store, repo = await _new_repo()

    await _save(repo, _make_channel("c1", max_steps=128, last_ref=None), 5)

    # Two writers both computed against prev=5. Winner writes i=7 first.
    status_a, _ = await _save(repo, _make_channel("c1", max_steps=128, last_ref=5), 7)
    assert status_a == 1

    # The straggler (i=6) is now stale versus the committed 7 and must be rejected.
    status_b, ref_b = await _save(
        repo, _make_channel("c1", max_steps=128, last_ref=5), 6
    )
    assert status_b == 0
    assert ref_b == 7
    assert await _stored_ref(store, "c1") == 7


@pytest.mark.asyncio
async def test_first_opt_save_rejects_reference_beyond_max_steps() -> None:
    store, repo = await _new_repo()

    status, _ = await _save(repo, _make_channel("c1", max_steps=128, last_ref=None), 200)
    assert status == 3
    assert await _stored_ref(store, "c1") is None


@pytest.mark.asyncio
async def test_first_opt_save_registers_new_channel_in_indexes() -> None:
    store, repo = await _new_repo()

    status, _ = await _save(repo, _make_channel("c1", max_steps=128, last_ref=None), 1)
    assert status == 1

    assert "c1" in await store.zrevrange("payment_channels:all", 0, -1)
    assert "c1" in await store.zrevrange("payment_channels:open", 0, -1)
    assert "c1" not in await store.zrevrange("payment_channels:closed", 0, -1)
