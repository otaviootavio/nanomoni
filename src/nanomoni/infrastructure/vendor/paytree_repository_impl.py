"""PayTree repository implementation."""

from __future__ import annotations

from typing import Optional

from ...domain.vendor.entities import PaytreePaymentChannel, PaytreeState
from ...domain.vendor.paytree_repository import PaytreeRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


class PaytreeRepositoryImpl(PaymentChannelRepositoryBaseImpl, PaytreeRepository):
    """KeyValueStore implementation for PayTree payment channels."""

    async def get_paytree_state(self, channel_id: str) -> Optional[PaytreeState]:
        key = f"paytree_state:latest:{channel_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaytreeState.model_validate_json(raw)

    async def get_paytree_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaytreePaymentChannel], Optional[PaytreeState]]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"paytree_state:latest:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, state_key])
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

        latest_key = f"paytree_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_paytree_payment",
            keys=[latest_key, channel_key],
            args=[payload_json, str(new_state.i)],
        )

        code = (
            int(result[0])
            if result and result[0] is not None and result[0] != ""
            else 0
        )
        payload = (
            result[1] if len(result) > 1 and result[1] and result[1] != "" else None
        )

        if code == 1:
            if payload is None:
                raise RuntimeError(
                    "Unexpected: save_paytree_payment returned success but no payload"
                )
            return 1, PaytreeState.model_validate_json(payload)
        elif code == 0:
            return 0, PaytreeState.model_validate_json(payload) if payload else None
        elif code == 3:
            return 3, PaytreeState.model_validate_json(payload) if payload else None
        else:
            return 2, None

    async def save_channel_and_initial_paytree_state(
        self, channel: PaytreePaymentChannel, initial_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"paytree_state:latest:{channel.channel_id}"

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_paytree_state",
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None
