"""Payment channel repository implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...domain.issuer.entities import PaymentChannel
from ...domain.issuer.repositories import PaymentChannelRepository
from ..storage import KeyValueStore


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """Payment channel repository backed by KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    @staticmethod
    def _channel_key_by_id(channel_id: UUID) -> str:
        return f"payment_channel:{channel_id}"

    @staticmethod
    def _computed_id_key(computed_id: str) -> str:
        return f"payment_channel:computed:{computed_id}"

    async def create(self, channel: PaymentChannel) -> PaymentChannel:
        # store by id
        await self.store.set(
            self._channel_key_by_id(channel.id), channel.model_dump_json()
        )
        # index by computed id
        await self.store.set(
            self._computed_id_key(channel.computed_id), str(channel.id)
        )
        return channel

    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        channel_id = await self.store.get(self._computed_id_key(computed_id))
        if not channel_id:
            return None
        data = await self.store.get(self._channel_key_by_id(UUID(channel_id)))
        if not data:
            return None
        return PaymentChannel.model_validate_json(data)

    async def mark_closed(
        self,
        computed_id: str,
        close_payload_b64: str,
        client_close_signature_b64: str,
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannel:
        existing = await self.get_by_computed_id(computed_id)
        if not existing:
            raise ValueError("Payment channel not found")
        if existing.is_closed:
            return existing
        existing.is_closed = True
        existing.close_payload_b64 = close_payload_b64
        existing.client_close_signature_b64 = client_close_signature_b64
        existing.vendor_close_signature_b64 = vendor_close_signature_b64
        existing.closed_at = datetime.now(timezone.utc)
        existing.amount = amount
        existing.balance = balance
        await self.store.set(
            self._channel_key_by_id(existing.id), existing.model_dump_json()
        )
        return existing
