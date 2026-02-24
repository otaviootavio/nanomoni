"""PayWord repository implementation."""

from __future__ import annotations

from typing import Optional

from ...domain.vendor.entities import PaywordPaymentChannel, PaywordState
from ...domain.vendor.payword_repository import PaywordRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


class PaywordRepositoryImpl(PaymentChannelRepositoryBaseImpl, PaywordRepository):
    """KeyValueStore implementation for PayWord payment channels."""

    async def get_payword_state(self, channel_id: str) -> Optional[PaywordState]:
        key = f"payword_state:latest:{channel_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaywordState.model_validate_json(raw)

    async def get_payword_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaywordPaymentChannel], Optional[PaywordState]]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"payword_state:latest:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, state_key])
        if not channel_json:
            return None, None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaywordPaymentChannel):
            raise TypeError("Payment channel is not PayWord-enabled")
        state = PaywordState.model_validate_json(state_json) if state_json else None
        return channel, state

    async def save_payword_payment(
        self, channel: PaywordPaymentChannel, new_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        if channel.channel_id != new_state.channel_id:
            raise ValueError("Channel channel_id mismatch for PayWord payment")

        latest_key = f"payword_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_payword_payment",
            keys=[latest_key, channel_key],
            args=[payload_json, str(new_state.k)],
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
                    "Unexpected: save_payword_payment returned success but no payload"
                )
            return 1, PaywordState.model_validate_json(payload)
        elif code == 0:
            return 0, PaywordState.model_validate_json(payload) if payload else None
        elif code == 3:
            return 3, PaywordState.model_validate_json(payload) if payload else None
        else:
            return 2, None

    async def save_channel_and_initial_payword_state(
        self, channel: PaywordPaymentChannel, initial_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"payword_state:latest:{channel.channel_id}"

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_payword_state",
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None
