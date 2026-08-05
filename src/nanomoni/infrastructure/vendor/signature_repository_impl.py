"""Signature repository implementation."""

from __future__ import annotations

from typing import Optional

from ...domain.vendor.entities import SignaturePaymentChannel, SignatureState
from ...domain.vendor.signature_repository import SignatureRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


class SignatureRepositoryImpl(PaymentChannelRepositoryBaseImpl, SignatureRepository):
    """KeyValueStore implementation for signature payment channels."""

    async def save_payment(
        self, channel: SignaturePaymentChannel, new_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        latest_key = f"signature_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_signature_payment",
            keys=[latest_key, channel_key],
            args=[
                payload_json,
                str(new_state.cumulative_owed_amount),
                str(channel.amount),
            ],
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
                    "Unexpected: save_payment returned success but no payload"
                )
            return 1, SignatureState.model_validate_json(payload)
        elif code == 0:
            return 0, SignatureState.model_validate_json(payload) if payload else None
        else:
            return 2, None

    async def save_channel_and_initial_payment(
        self, channel: SignaturePaymentChannel, initial_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"signature_state:latest:{channel.channel_id}"

        channel.signature_state = None
        channel_json = channel.model_dump_json(exclude={"signature_state"})
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_payment",
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None
