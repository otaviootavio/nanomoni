"""PayTree repository implementation."""

from __future__ import annotations

from typing import Optional

from ...domain.vendor.entities import PaytreePaymentChannel, PaytreeState
from ...domain.vendor.paytree_repository import PaytreeRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


class PaytreeRepositoryImpl(PaymentChannelRepositoryBaseImpl, PaytreeRepository):
    """KeyValueStore implementation for PayTree payment channels."""

    async def get_paytree_pruned_channel_state(
        self, channel_id: str
    ) -> Optional[PaytreePaymentChannel]:
        """Get pruned channel state (channel metadata only; no proof)."""
        channel_key = f"payment_channel:{channel_id}"
        channel_json = await self.store.get(channel_key)
        if not channel_json:
            return None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreePaymentChannel):
            raise TypeError("Payment channel is not PayTree-enabled")
        return channel

    async def get_paytree_state(self, channel_id: str) -> Optional[PaytreeState]:
        key = f"paytree_proof:{channel_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaytreeState.model_validate_json(raw)

    async def get_paytree_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaytreePaymentChannel], Optional[PaytreeState]]:
        channel_key = f"payment_channel:{channel_id}"
        proof_key = f"paytree_proof:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, proof_key])
        if not channel_json:
            return None, None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreePaymentChannel):
            raise TypeError("Payment channel is not PayTree-enabled")
        state = PaytreeState.model_validate_json(state_json) if state_json else None
        return channel, state

    async def save_paytree_payment(
        self, channel: PaytreePaymentChannel, new_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        if channel.channel_id != new_state.channel_id:
            raise ValueError("Channel channel_id mismatch for PayTree payment")

        proof_key = f"paytree_proof:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_paytree_payment",
            keys=[channel_key, proof_key],
            args=[
                payload_json,
                str(new_state.i),
                new_state.leaf_b64,
                new_state.created_at.isoformat(),
            ],
        )

        code = (
            int(result[0])
            if result and result[0] is not None and result[0] != ""
            else 0
        )
        if code == 1:
            # Script returns a minimal ack; use the in-memory state we just validated.
            return 1, new_state
        elif code == 0:
            # Stale/race. Fetch full proof only on this slow path.
            return 0, await self.get_paytree_state(new_state.channel_id)
        elif code == 3:
            return 3, await self.get_paytree_state(new_state.channel_id)
        else:
            return 2, None

    async def save_channel_and_initial_paytree_state(
        self, channel: PaytreePaymentChannel, initial_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        proof_key = f"paytree_proof:{channel.channel_id}"

        # Ensure initial state is reflected in channel metadata (pruned state for duplicate check without proof fetch)
        channel.last_leaf_index = initial_state.i
        channel.last_leaf_b64 = initial_state.leaf_b64
        channel.last_paytree_created_at = initial_state.created_at

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_paytree_pruned_state",
            keys=[channel_key, proof_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None
