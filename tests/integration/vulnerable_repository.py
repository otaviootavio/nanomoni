"""Deliberately vulnerable PaymentChannel repository implementation for testing.

DO NOT USE IN PRODUCTION. This exists only to prove the race condition
is real and that our atomic implementation fixes it.
"""

from __future__ import annotations

from typing import Optional

from nanomoni.domain.vendor.entities import OffChainTx, PaymentChannel
from nanomoni.infrastructure.storage import KeyValueStore
from nanomoni.infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)


class VulnerablePaymentChannelRepositoryImpl(PaymentChannelRepositoryImpl):
    """
    DELIBERATELY VULNERABLE implementation that demonstrates the lost update bug.

    This implementation uses a non-atomic read-check-write pattern that is
    susceptible to TOCTOU (Time-of-Check to Time-of-Use) race conditions.

    DO NOT USE THIS IN PRODUCTION. This exists only to prove the race condition
    is real and that our atomic implementation fixes it.
    """

    def __init__(self, store: KeyValueStore):
        super().__init__(store)

    async def save_payment(
        self, channel: PaymentChannel, new_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        VULNERABLE: Non-atomic read-check-write implementation.

        This method has a TOCTOU race condition:
        1. READ: Get current transaction
        2. CHECK: Compare amounts (in Python, not Redis)
        3. WRITE: Store new transaction

        Between steps 1-2 and 2-3, another request can interleave,
        causing a lost update where a higher payment is overwritten
        by a lower one.
        """
        latest_key = f"off_chain_tx:latest:{new_tx.computed_id}"
        channel_key = f"payment_channel:{new_tx.computed_id}"

        # Step 1: READ channel (check exists)
        channel_raw = await self.store.get(channel_key)
        if not channel_raw:
            return 2, None

        channel = PaymentChannel.model_validate_json(channel_raw)

        # Check capacity
        if new_tx.owed_amount > channel.amount:
            current_raw = await self.store.get(latest_key)
            current = (
                OffChainTx.model_validate_json(current_raw) if current_raw else None
            )
            return 0, current

        # Step 2: READ current transaction
        # ⚠️ RACE WINDOW STARTS HERE ⚠️
        current_raw = await self.store.get(latest_key)

        if not current_raw:
            # First payment - just store it
            # ⚠️ Another "first payment" could have been stored between READ and WRITE
            await self.store.set(latest_key, new_tx.model_dump_json())
            return 1, new_tx

        current = OffChainTx.model_validate_json(current_raw)

        # Step 3: CHECK in Python (not atomic with read or write)
        if new_tx.owed_amount > current.owed_amount:
            # ⚠️ RACE WINDOW: Another request could have updated between CHECK and WRITE
            # Step 4: WRITE (not atomic with check)
            await self.store.set(latest_key, new_tx.model_dump_json())
            # ⚠️ RACE WINDOW ENDS HERE ⚠️
            return 1, new_tx
        else:
            return 0, current
