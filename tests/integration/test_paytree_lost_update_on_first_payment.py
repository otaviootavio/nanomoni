"""Integration test for PayTree state monotonicity on FIRST payment.

This test uses real Redis and validates that concurrent PayTree state updates
do not lose the larger i value (atomic Lua script).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from nanomoni.domain.vendor.entities import PaymentChannel, PaytreeState
from nanomoni.infrastructure.storage import RedisKeyValueStore
from nanomoni.infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)


@pytest.mark.asyncio
async def test_paytree_state_first_payment_no_lost_update(
    redis_store: RedisKeyValueStore,
) -> None:
    repo = PaymentChannelRepositoryImpl(redis_store)

    computed_id = f"test_paytree_first_{uuid.uuid4().hex[:8]}"
    channel = PaymentChannel(
        computed_id=computed_id,
        client_public_key_der_b64="client_pk",
        vendor_public_key_der_b64="vendor_pk",
        salt_b64="salt",
        amount=100,
        balance=0,
        is_closed=False,
        paytree_root_b64="root_b64",
        paytree_unit_value=1,
        paytree_max_i=100,
        paytree_hash_alg="sha256",
    )
    await repo.save_channel(channel)

    # Two concurrent first-paytree-state attempts: i=20 and i=25.
    state_a = PaytreeState(
        computed_id=computed_id,
        i=20,
        leaf_b64="leafA",
        siblings_b64=["sib1", "sib2"],
    )
    state_b = PaytreeState(
        computed_id=computed_id,
        i=25,
        leaf_b64="leafB",
        siblings_b64=["sib1", "sib2"],
    )

    task_a = asyncio.create_task(repo.save_paytree_payment(channel, state_a))
    task_b = asyncio.create_task(repo.save_paytree_payment(channel, state_b))
    await asyncio.gather(task_a, task_b)

    latest = await repo.get_paytree_state(computed_id)
    assert latest is not None
    assert latest.i == 25
