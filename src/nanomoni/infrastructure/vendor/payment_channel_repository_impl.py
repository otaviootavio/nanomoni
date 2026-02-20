"""PaymentChannel repository implementation over a storage abstraction."""

from __future__ import annotations

import json
from typing import Optional

from ...domain.vendor.entities import (
    PaymentChannelBase,
    PaytreeFirstOptPaymentChannel,
    PaytreeFirstOptState,
    PaytreePaymentChannel,
    PaytreeSecondOptPaymentChannel,
    PaytreeSecondOptState,
    PaytreeState,
    PaywordPaymentChannel,
    PaywordState,
    SignatureState,
    SignaturePaymentChannel,
)
from ...domain.vendor.payment_channel_repository import PaymentChannelRepository
from ..storage import KeyValueStore


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """PaymentChannel repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def save_channel(
        self, payment_channel: PaymentChannelBase
    ) -> PaymentChannelBase:
        """
        Store vendor-side cached channels keyed directly by channel_id to
        avoid extra lookups.

        Keys:
          - payment_channel:{channel_id} -> PaymentChannel JSON
          - payment_channels:all|open|closed -> sorted sets of channel_id
        """
        channel_key = f"payment_channel:{payment_channel.channel_id}"
        existing = await self.store.get(channel_key)
        if existing is not None:
            raise ValueError("Payment channel with this channel_id already exists")

        if isinstance(payment_channel, SignaturePaymentChannel):
            # Ensure signature_state is None when caching for the first time
            payment_channel.signature_state = None
            # Exclude signature_state from storage to avoid leaking aggregate structure
            # into the static metadata key
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

    def _deserialize_channel(self, raw: str) -> PaymentChannelBase:
        data = json.loads(raw)
        if data.get("payword_root_b64"):
            return PaywordPaymentChannel.model_validate(data)
        if data.get("paytree_first_opt_root_b64"):
            return PaytreeFirstOptPaymentChannel.model_validate(data)
        if data.get("paytree_second_opt_root_b64"):
            return PaytreeSecondOptPaymentChannel.model_validate(data)
        if data.get("paytree_root_b64"):
            return PaytreePaymentChannel.model_validate(data)
        return SignaturePaymentChannel.model_validate(data)

    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannelBase]:
        """
        Get the full channel aggregate (metadata + latest state).
        Uses MGET to fetch both keys in a single round trip.
        """
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

    async def save_payment(
        self, channel: SignaturePaymentChannel, new_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        """
        Atomically update the channel's latest signature state using Lua script.
        """
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

    async def save_payword_payment(
        self, channel: PaywordPaymentChannel, new_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically update the channel's latest PayWord state using Lua script.
        """
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

    async def save_channel_and_initial_payment(
        self, channel: SignaturePaymentChannel, initial_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        """
        Atomically save channel metadata AND the first signature state.
        """
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"signature_state:latest:{channel.channel_id}"

        # Prepare channel JSON (excluding latest_tx as per our pattern)
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
        # payload = result[1]

        if code == 1:
            return 1, initial_state
        else:
            # Race condition: channel or tx already exists
            return 0, None

    async def save_channel_and_initial_payword_state(
        self, channel: PaywordPaymentChannel, initial_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically save channel metadata AND the first PayWord state.
        """
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
        else:
            return 0, None

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

        # Keep dynamic latest state out of the static channel record to avoid duplication.
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
        from datetime import datetime, timezone

        channel.closed_at = datetime.now(timezone.utc)

        return await self.update(channel)

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
        """
        Atomically update the channel's latest PayTree state using Lua script.
        """
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
        """
        Atomically save channel metadata AND the first PayTree state.
        """
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
        else:
            return 0, None

    async def get_paytree_first_opt_state(
        self, channel_id: str
    ) -> Optional[PaytreeFirstOptState]:
        key = f"paytree_first_opt_state:latest:{channel_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaytreeFirstOptState.model_validate_json(raw)

    async def get_paytree_first_opt_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaytreeFirstOptPaymentChannel], Optional[PaytreeFirstOptState]]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"paytree_first_opt_state:latest:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, state_key])
        if not channel_json:
            return None, None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreeFirstOptPaymentChannel):
            raise TypeError("Payment channel is not PayTree First Opt-enabled")
        state = (
            PaytreeFirstOptState.model_validate_json(state_json) if state_json else None
        )
        return channel, state

    async def save_paytree_first_opt_payment(
        self, channel: PaytreeFirstOptPaymentChannel, new_state: PaytreeFirstOptState
    ) -> tuple[int, Optional[PaytreeFirstOptState]]:
        if channel.channel_id != new_state.channel_id:
            raise ValueError(
                "Channel channel_id mismatch for PayTree First Opt payment"
            )

        latest_key = f"paytree_first_opt_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_paytree_first_opt_payment",
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
                    "Unexpected: save_paytree_first_opt_payment returned success but no payload"
                )
            return 1, PaytreeFirstOptState.model_validate_json(payload)
        elif code == 0:
            return (
                0,
                PaytreeFirstOptState.model_validate_json(payload) if payload else None,
            )
        elif code == 3:
            return (
                3,
                PaytreeFirstOptState.model_validate_json(payload) if payload else None,
            )
        else:
            return 2, None

    async def save_channel_and_initial_paytree_first_opt_state(
        self,
        channel: PaytreeFirstOptPaymentChannel,
        initial_state: PaytreeFirstOptState,
    ) -> tuple[int, Optional[PaytreeFirstOptState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"paytree_first_opt_state:latest:{channel.channel_id}"

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_paytree_first_opt_state",
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )
        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None

    async def get_paytree_second_opt_state(
        self, channel_id: str
    ) -> Optional[PaytreeSecondOptState]:
        key = f"paytree_second_opt_state:latest:{channel_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaytreeSecondOptState.model_validate_json(raw)

    async def get_paytree_second_opt_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[
        Optional[PaytreeSecondOptPaymentChannel], Optional[PaytreeSecondOptState]
    ]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"paytree_second_opt_state:latest:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, state_key])
        if not channel_json:
            return None, None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise TypeError("Payment channel is not PayTree Second Opt-enabled")
        state = (
            PaytreeSecondOptState.model_validate_json(state_json)
            if state_json
            else None
        )
        return channel, state

    async def save_paytree_second_opt_payment(
        self, channel: PaytreeSecondOptPaymentChannel, new_state: PaytreeSecondOptState
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        if channel.channel_id != new_state.channel_id:
            raise ValueError(
                "Channel channel_id mismatch for PayTree Second Opt payment"
            )

        latest_key = f"paytree_second_opt_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.run_script(
            "save_paytree_second_opt_payment",
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
                    "Unexpected: save_paytree_second_opt_payment returned success but no payload"
                )
            return 1, PaytreeSecondOptState.model_validate_json(payload)
        elif code == 0:
            return (
                0,
                PaytreeSecondOptState.model_validate_json(payload) if payload else None,
            )
        elif code == 3:
            return (
                3,
                PaytreeSecondOptState.model_validate_json(payload) if payload else None,
            )
        else:
            return 2, None

    async def save_channel_and_initial_paytree_second_opt_state(
        self,
        channel: PaytreeSecondOptPaymentChannel,
        initial_state: PaytreeSecondOptState,
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"paytree_second_opt_state:latest:{channel.channel_id}"

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.run_script(
            "save_channel_and_initial_paytree_second_opt_state",
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id],
        )
        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None
