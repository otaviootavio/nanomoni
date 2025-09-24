"""PaymentChannel repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ...domain.vendor.entities import PaymentChannel
from ...domain.vendor.payment_channel_repository import PaymentChannelRepository
from ..storage import KeyValueStore


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """PaymentChannel repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, payment_channel: PaymentChannel) -> PaymentChannel:
        computed_id_key = f"payment_channel:computed_id:{payment_channel.computed_id}"
        existing = await self.store.get(computed_id_key)
        if existing is not None:
            raise ValueError("Payment channel with this computed_id already exists")

        channel_key = f"payment_channel:{payment_channel.id}"
        await self.store.set(channel_key, payment_channel.model_dump_json())

        await self.store.set(computed_id_key, str(payment_channel.id))

        created_ts = payment_channel.created_at.timestamp()
        await self.store.zadd(
            "payment_channels:all", {str(payment_channel.id): created_ts}
        )

        if not payment_channel.is_closed:
            await self.store.zadd(
                "payment_channels:open", {str(payment_channel.id): created_ts}
            )
        else:
            await self.store.zadd(
                "payment_channels:closed", {str(payment_channel.id): created_ts}
            )

        return payment_channel

    async def get_by_id(self, channel_id: UUID) -> Optional[PaymentChannel]:
        channel_key = f"payment_channel:{channel_id}"
        data = await self.store.get(channel_key)
        if not data:
            return None
        return PaymentChannel.model_validate_json(data)

    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        computed_id_key = f"payment_channel:computed_id:{computed_id}"
        channel_id = await self.store.get(computed_id_key)
        if not channel_id:
            return None

        data = await self.store.get(f"payment_channel:{channel_id}")
        if not data:
            return None
        return PaymentChannel.model_validate_json(data)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[PaymentChannel]:
        ids: list[str] = await self.store.zrevrange(
            "payment_channels:all", skip, skip + limit - 1
        )
        channels: List[PaymentChannel] = []
        for channel_id in ids:
            data = await self.store.get(f"payment_channel:{channel_id}")
            if data:
                channels.append(PaymentChannel.model_validate_json(data))
        return channels

    async def update(self, payment_channel: PaymentChannel) -> PaymentChannel:
        channel_key = f"payment_channel:{payment_channel.id}"

        existing_raw = await self.store.get(channel_key)
        old_is_closed: Optional[bool] = None
        if existing_raw:
            existing_channel = PaymentChannel.model_validate_json(existing_raw)
            old_is_closed = existing_channel.is_closed

        await self.store.set(channel_key, payment_channel.model_dump_json())

        if old_is_closed is not None and old_is_closed != payment_channel.is_closed:
            created_ts = payment_channel.created_at.timestamp()
            if payment_channel.is_closed:
                await self.store.zrem("payment_channels:open", str(payment_channel.id))
                await self.store.zadd(
                    "payment_channels:closed", {str(payment_channel.id): created_ts}
                )
            else:
                await self.store.zrem(
                    "payment_channels:closed", str(payment_channel.id)
                )
                await self.store.zadd(
                    "payment_channels:open", {str(payment_channel.id): created_ts}
                )

        return payment_channel

    async def mark_closed(
        self,
        computed_id: str,
        close_payload_b64: str,
        client_close_signature_b64: str,
        vendor_close_signature_b64: str,
        *,
        amount: int,
        balance: int,
    ) -> PaymentChannel:
        channel = await self.get_by_computed_id(computed_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return channel

        channel.is_closed = True
        channel.close_payload_b64 = close_payload_b64
        channel.client_close_signature_b64 = client_close_signature_b64
        channel.vendor_close_signature_b64 = vendor_close_signature_b64
        channel.amount = amount
        channel.balance = balance
        from datetime import datetime, timezone

        channel.closed_at = datetime.now(timezone.utc)

        return await self.update(channel)
