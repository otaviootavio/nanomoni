"""Payment channel repository implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ...domain.issuer.entities import (
    PaymentChannelBase,
    PaytreePaymentChannel,
    PaywordPaymentChannel,
    SignaturePaymentChannel,
)
from ...domain.issuer.repositories import PaymentChannelRepository
from ..storage import KeyValueStore


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """Payment channel repository backed by KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    @staticmethod
    def _channel_id_key(channel_id: str) -> str:
        # Key channels directly by channel_id to avoid an extra id lookup.
        return f"payment_channel:{channel_id}"

    async def create(self, channel: PaymentChannelBase) -> PaymentChannelBase:
        # Store channel JSON keyed directly by channel_id.
        # Use a Lua script to ensure we don't overwrite an existing channel.
        key = self._channel_id_key(channel.channel_id)
        script = (
            "if redis.call('EXISTS', KEYS[1]) == 1 then "
            "  return 0 "
            "end "
            "redis.call('SET', KEYS[1], ARGV[1]) "
            "return 1"
        )
        created = await self.store.eval(
            script, keys=[key], args=[channel.model_dump_json()]
        )
        if int(created) != 1:
            raise ValueError("Payment channel already exists")
        return channel

    def _deserialize_channel(self, raw: str) -> PaymentChannelBase:
        data = json.loads(raw)
        if data.get("payword_root_b64"):
            return PaywordPaymentChannel.model_validate(data)
        if data.get("paytree_root_b64"):
            return PaytreePaymentChannel.model_validate(data)
        return SignaturePaymentChannel.model_validate(data)

    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannelBase]:
        data = await self.store.get(self._channel_id_key(channel_id))
        if not data:
            return None
        return self._deserialize_channel(data)

    async def delete_by_channel_id(self, channel_id: str) -> int:
        return await self.store.delete(self._channel_id_key(channel_id))

    async def mark_closed(
        self,
        channel_id: str,
        close_payload_b64: Optional[str],
        client_close_signature_b64: Optional[str],
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannelBase:
        existing = await self.get_by_channel_id(channel_id)
        if not existing:
            raise ValueError("Payment channel not found")
        if existing.is_closed:
            return existing
        existing.is_closed = True
        if isinstance(existing, SignaturePaymentChannel):
            existing.close_payload_b64 = close_payload_b64
            existing.client_close_signature_b64 = client_close_signature_b64
        existing.vendor_close_signature_b64 = vendor_close_signature_b64
        existing.closed_at = datetime.now(timezone.utc)
        existing.amount = amount
        existing.balance = balance
        await self.store.set(
            self._channel_id_key(existing.channel_id), existing.model_dump_json()
        )
        return existing
