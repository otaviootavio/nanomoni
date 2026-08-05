"""PaymentRepositoryImpl — unified payment repository for proof-based channels."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import ValidationError

from ...domain.shared.crypto_proof import CryptoProof
from ...domain.vendor.entities import PaymentChannel, PaymentState
from ...domain.vendor.payment_repository import PaymentRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


class PaymentRepositoryImpl(PaymentChannelRepositoryBaseImpl, PaymentRepository):
    """KeyValueStore implementation for unified PaymentChannel + PaymentState."""

    def _parse_channel(self, raw: str) -> Optional[PaymentChannel]:
        """Parse a stored channel in a single pass.

        Every channel this repository owns is a ``PaymentChannel``, so it can
        validate straight from JSON instead of going through the base class's
        ``_deserialize_channel``, which spends an extra Python ``json.loads``
        pass just to read ``scheme`` and pick a model. Anything that isn't a
        proof-based channel falls back to that dispatch, which distinguishes a
        signature-mode channel stored under the same key (not found, as before)
        from genuinely corrupt data (raises, as before).
        """
        try:
            return PaymentChannel.model_validate_json(raw)
        except ValidationError:
            channel = self._deserialize_channel(raw)
            return channel if isinstance(channel, PaymentChannel) else None

    async def get_channel(self, channel_id: str) -> Optional[PaymentChannel]:
        raw = await self.store.get(f"payment_channel:{channel_id}")
        if not raw:
            return None
        return self._parse_channel(raw)

    async def get_state(self, channel_id: str) -> Optional[PaymentState]:
        raw = await self.store.get(f"payment_state:{channel_id}")
        if not raw:
            return None
        return PaymentState.model_validate_json(raw)

    async def get_channel_and_state(
        self, channel_id: str
    ) -> tuple[Optional[PaymentChannel], Optional[PaymentState]]:
        channel_raw, state_raw = await self.store.mget(
            [f"payment_channel:{channel_id}", f"payment_state:{channel_id}"]
        )
        channel = self._parse_channel(channel_raw) if channel_raw else None
        state: Optional[PaymentState] = None
        if state_raw:
            state = PaymentState.model_validate_json(state_raw)
        return channel, state

    async def save_payment(
        self,
        channel: PaymentChannel,
        new_state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[PaymentState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        state_key = f"payment_state:{channel.channel_id}"
        proof_key = f"crypto_proof:{channel.channel_id}"

        state_json = new_state.model_dump_json()
        proof_json = json.dumps({"scheme": proof.scheme.value, **proof.data})

        result = await self.store.run_script(
            "save_payment",
            keys=[channel_key, state_key, proof_key],
            args=[str(new_state.proof_reference), state_json, proof_json],
        )

        code = int(result[0]) if result and result[0] is not None else 0
        if code == 1:
            return 1, new_state
        if code == 0:
            # The script's stale branch returns only the previous ref
            # (tostring(prev)), not the full state, so reconstructing the
            # current PaymentState needs this extra read.
            return 0, await self.get_state(channel.channel_id)
        if code == 3:
            # Unlike the stale branch, the capacity-exceeded branch already
            # returns the full current state JSON (or '' if none), so it can
            # be parsed directly instead of spending a second round trip.
            raw = result[1] if result and len(result) > 1 else None
            state = PaymentState.model_validate_json(raw) if raw else None
            return 3, state
        return 2, None

    async def save_channel_and_initial_state(
        self,
        channel: PaymentChannel,
        state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[PaymentState]]:
        # Embed first payment reference in channel before persisting
        channel.last_proof_reference = state.proof_reference
        channel_key = f"payment_channel:{channel.channel_id}"
        state_key = f"payment_state:{channel.channel_id}"
        proof_key = f"crypto_proof:{channel.channel_id}"

        channel_json = channel.model_dump_json()
        state_json = state.model_dump_json()
        proof_json = json.dumps({"scheme": proof.scheme.value, **proof.data})
        created_ts = str(channel.created_at.timestamp())

        result = await self.store.run_script(
            "save_channel_and_initial_payment_unified",
            keys=[channel_key, state_key, proof_key],
            args=[channel_json, state_json, proof_json, created_ts, channel.channel_id],
        )

        code = int(result[0]) if result and result[0] is not None else 0
        if code == 1:
            return 1, state
        return 0, None

    async def get_crypto_proof_raw(self, channel_id: str) -> Optional[str]:
        return await self.store.get(f"crypto_proof:{channel_id}")
