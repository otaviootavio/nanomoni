"""Integration test for PayWord state monotonicity on FIRST payment.

This test uses real Redis and validates that concurrent PayWord state updates
do not lose the larger k value (atomic Lua script).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from nanomoni.domain.vendor.entities import PaymentChannel, PaywordState
from nanomoni.infrastructure.storage import RedisKeyValueStore
from nanomoni.infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)


@pytest.mark.asyncio
async def test_payword_state_first_payment_no_lost_update(
    redis_store: RedisKeyValueStore,
) -> None:
    repo = PaymentChannelRepositoryImpl(redis_store)

    computed_id = f"test_payword_first_{uuid.uuid4().hex[:8]}"
    channel = PaymentChannel(
        computed_id=computed_id,
        client_public_key_der_b64="client_pk",
        vendor_public_key_der_b64="vendor_pk",
        salt_b64="salt",
        amount=100,
        balance=0,
        is_closed=False,
        payword_root_b64="root_b64",
        payword_unit_value=1,
        payword_max_k=100,
        payword_hash_alg="sha256",
    )
    await repo.save_channel(channel)

    # Two concurrent first-payword-state attempts: k=20 and k=25.
    state_a = PaywordState(computed_id=computed_id, k=20, token_b64="tokenA")
    state_b = PaywordState(computed_id=computed_id, k=25, token_b64="tokenB")

    task_a = asyncio.create_task(repo.save_payword_payment(channel, state_a))
    task_b = asyncio.create_task(repo.save_payword_payment(channel, state_b))
    await asyncio.gather(task_a, task_b)

    latest = await repo.get_payword_state(computed_id)
    assert latest is not None
    assert latest.k == 25
