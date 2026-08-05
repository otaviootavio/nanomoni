"""Base implementation for payment channel repositories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ...domain.vendor.entities import (
    PaymentChannel,
    PaymentChannelBase,
    SignaturePaymentChannel,
    SignatureState,
)
from ...domain.vendor.payment_channel_repository_base import (
    PaymentChannelRepositoryBase,
)
from ..storage import KeyValueStore


class PaymentChannelRepositoryBaseImpl(PaymentChannelRepositoryBase):
    """Base implementation with shared storage logic."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    def _deserialize_channel(self, raw: str) -> PaymentChannelBase:
        data = json.loads(raw)
        if data.get("scheme") in ("payword", "paytree", "paytree_child_pair"):
            return PaymentChannel.model_validate(data)
        return SignaturePaymentChannel.model_validate(data)

    async def save_channel(
        self, payment_channel: PaymentChannelBase
    ) -> PaymentChannelBase:
        channel_key = f"payment_channel:{payment_channel.channel_id}"
        existing = await self.store.get(channel_key)
        if existing is not None:
            raise ValueError("Payment channel with this channel_id already exists")

        if isinstance(payment_channel, SignaturePaymentChannel):
            payment_channel.signature_state = None
            channel_json = payment_channel.model_dump_json(exclude={"signature_state"})
        else:
            channel_json = payment_channel.model_dump_json()

        await self.store.set(channel_key, channel_json)

        created_ts = payment_channel.created_at.timestamp()
        await self.store.zadd(
            "payment_channels:all", {payment_channel.channel_id: created_ts}
        )

        if not payment_channel.is_closed:
            await self.store.zadd(
                "payment_channels:open", {payment_channel.channel_id: created_ts}
            )
        else:
            await self.store.zadd(
                "payment_channels:closed", {payment_channel.channel_id: created_ts}
            )

        return payment_channel

    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannelBase]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"signature_state:latest:{channel_id}"

        results = await self.store.mget([channel_key, state_key])
        channel_json = results[0]
        state_json = results[1]

        if not channel_json:
            return None

        channel = self._deserialize_channel(channel_json)

        if isinstance(channel, SignaturePaymentChannel):
            if state_json:
                channel.signature_state = SignatureState.model_validate_json(state_json)
            else:
                channel.signature_state = None

        return channel

    async def get_all(
        self, skip: int = 0, limit: int = 100
    ) -> list[PaymentChannelBase]:
        ids: list[str] = await self.store.zrevrange(
            "payment_channels:all", skip, skip + limit - 1
        )
        if not ids:
            return []

        keys = [f"payment_channel:{channel_id}" for channel_id in ids]
        results = await self.store.mget(keys)

        channels: list[PaymentChannelBase] = []
        for data in results:
            if data:
                channels.append(self._deserialize_channel(data))
        return channels

    async def update(self, payment_channel: PaymentChannelBase) -> PaymentChannelBase:
        channel_key = f"payment_channel:{payment_channel.channel_id}"

        existing_raw = await self.store.get(channel_key)
        old_is_closed: Optional[bool] = None
        if existing_raw:
            existing_channel = self._deserialize_channel(existing_raw)
            old_is_closed = existing_channel.is_closed

        if isinstance(payment_channel, SignaturePaymentChannel):
            await self.store.set(
                channel_key,
                payment_channel.model_dump_json(exclude={"signature_state"}),
            )
        else:
            await self.store.set(channel_key, payment_channel.model_dump_json())

        if old_is_closed is not None and old_is_closed != payment_channel.is_closed:
            created_ts = payment_channel.created_at.timestamp()
            if payment_channel.is_closed:
                await self.store.zrem(
                    "payment_channels:open", payment_channel.channel_id
                )
                await self.store.zadd(
                    "payment_channels:closed",
                    {payment_channel.channel_id: created_ts},
                )
            else:
                await self.store.zrem(
                    "payment_channels:closed", payment_channel.channel_id
                )
                await self.store.zadd(
                    "payment_channels:open", {payment_channel.channel_id: created_ts}
                )

        return payment_channel

    async def mark_closed(
        self,
        channel_id: str,
        *,
        amount: int,
        balance: int,
    ) -> PaymentChannelBase:
        channel = await self.get_by_channel_id(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return channel

        channel.is_closed = True
        channel.amount = amount
        channel.balance = balance
        channel.closed_at = datetime.now(timezone.utc)

        return await self.update(channel)
