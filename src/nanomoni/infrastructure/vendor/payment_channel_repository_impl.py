"""PaymentChannel repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional

from ...domain.vendor.entities import (
    PaymentChannel,
    OffChainTx,
    PaywordState,
    PaytreeState,
)
from ...domain.vendor.payment_channel_repository import PaymentChannelRepository
from ..storage import KeyValueStore


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """PaymentChannel repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def save_channel(self, payment_channel: PaymentChannel) -> PaymentChannel:
        """
        Store vendor-side cached channels keyed directly by computed_id to
        avoid extra lookups.

        Keys:
          - payment_channel:{computed_id} -> PaymentChannel JSON
          - payment_channels:all|open|closed -> sorted sets of computed_id
        """
        channel_key = f"payment_channel:{payment_channel.computed_id}"
        existing = await self.store.get(channel_key)
        if existing is not None:
            raise ValueError("Payment channel with this computed_id already exists")

        # Ensure latest_tx is None when caching for the first time
        payment_channel.latest_tx = None
        # Exclude latest_tx from storage to avoid leaking aggregate structure
        # into the static metadata key
        await self.store.set(
            channel_key, payment_channel.model_dump_json(exclude={"latest_tx"})
        )

        created_ts = payment_channel.created_at.timestamp()
        await self.store.zadd(
            "payment_channels:all", {payment_channel.computed_id: created_ts}
        )

        if not payment_channel.is_closed:
            await self.store.zadd(
                "payment_channels:open", {payment_channel.computed_id: created_ts}
            )
        else:
            await self.store.zadd(
                "payment_channels:closed", {payment_channel.computed_id: created_ts}
            )

        return payment_channel

    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        """
        Get the full channel aggregate (metadata + latest tx).
        Uses MGET to fetch both keys in a single round trip.
        """
        channel_key = f"payment_channel:{computed_id}"
        tx_key = f"off_chain_tx:latest:{computed_id}"

        results = await self.store.mget([channel_key, tx_key])

        channel_json = results[0]
        tx_json = results[1]

        if not channel_json:
            return None

        channel = PaymentChannel.model_validate_json(channel_json)

        if tx_json:
            channel.latest_tx = OffChainTx.model_validate_json(tx_json)
        else:
            channel.latest_tx = None

        return channel

    async def get_payword_state(self, computed_id: str) -> Optional[PaywordState]:
        key = f"payword_state:latest:{computed_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaywordState.model_validate_json(raw)

    async def save_payment(
        self, channel: PaymentChannel, new_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        Atomically update the channel's latest transaction using Lua script.
        """
        script = """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_amount = tonumber(ARGV[2])
        local channel_amount = tonumber(ARGV[3])

        -- Check channel existence (fast check via key existence or just rely on channel_amount)
        -- Since we pass channel_amount, we assume the caller verified the channel exists locally.
        -- But for strictness, we can check if the channel key exists.
        local channel_exists = redis.call('EXISTS', channel_key)
        if channel_exists == 0 then
            return {2, ''}
        end
        
        if new_amount > channel_amount then
            -- Channel capacity exceeded - get current tx for error reporting
            local current_raw = redis.call('GET', latest_key)
            return {0, current_raw or ''}
        end
        
        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end
        
        local current = cjson.decode(current_raw)
        local current_amount = tonumber(current.owed_amount)
        if new_amount > current_amount then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
        """

        latest_key = f"off_chain_tx:latest:{new_tx.computed_id}"
        channel_key = f"payment_channel:{new_tx.computed_id}"
        payload_json = new_tx.model_dump_json()

        result = await self.store.eval(
            script,
            keys=[latest_key, channel_key],
            args=[payload_json, str(new_tx.owed_amount), str(channel.amount)],
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
            return 1, OffChainTx.model_validate_json(payload)
        elif code == 0:
            return 0, OffChainTx.model_validate_json(payload) if payload else None
        else:
            return 2, None

    async def save_payword_payment(
        self, channel: PaymentChannel, new_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically update the channel's latest PayWord state using Lua script.
        """
        script = """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_k = tonumber(ARGV[2])

        -- Load and decode the stored channel to read max_k (atomic validation)
        local channel_raw = redis.call('GET', channel_key)
        if not channel_raw then
            return {2, ''}
        end
        local channel = cjson.decode(channel_raw)
        local max_k = tonumber(channel.payword_max_k or channel.max_k)
        if not max_k then
            -- Channel exists but is missing PayWord configuration
            return {2, ''}
        end
        if new_k > max_k then
            -- k exceeds PayWord commitment window
            local current_raw = redis.call('GET', latest_key)
            return {3, current_raw or ''}
        end

        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end

        local current = cjson.decode(current_raw)
        local current_k = tonumber(current.k)
        if new_k > current_k then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
        """

        if channel.computed_id != new_state.computed_id:
            raise ValueError("Channel computed_id mismatch for PayWord payment")

        latest_key = f"payword_state:latest:{new_state.computed_id}"
        channel_key = f"payment_channel:{new_state.computed_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.eval(
            script,
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
        self, channel: PaymentChannel, initial_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        Atomically save channel metadata AND the first transaction.
        """
        script = """
        local channel_key = KEYS[1]
        local latest_key = KEYS[2]
        local channel_json = ARGV[1]
        local tx_json = ARGV[2]
        local created_ts = tonumber(ARGV[3])
        local computed_id = ARGV[4]
        
        -- Check if channel already exists
        if redis.call('EXISTS', channel_key) == 1 then
            return {0, ''}
        end
        
        -- Check if tx already exists (shouldn't if channel doesn't, but for safety)
        if redis.call('EXISTS', latest_key) == 1 then
            return {0, ''}
        end
        
        -- 1. Save Channel Metadata
        redis.call('SET', channel_key, channel_json)
        
        -- 2. Save Initial Transaction
        redis.call('SET', latest_key, tx_json)
        
        -- 3. Update Indices
        redis.call('ZADD', 'payment_channels:all', created_ts, computed_id)
        redis.call('ZADD', 'payment_channels:open', created_ts, computed_id)
        
        return {1, tx_json}
        """

        channel_key = f"payment_channel:{channel.computed_id}"
        latest_key = f"off_chain_tx:latest:{channel.computed_id}"

        # Prepare channel JSON (excluding latest_tx as per our pattern)
        channel.latest_tx = None
        channel_json = channel.model_dump_json(exclude={"latest_tx"})
        tx_json = initial_tx.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.eval(
            script,
            keys=[channel_key, latest_key],
            args=[channel_json, tx_json, str(created_ts), channel.computed_id],
        )

        code = int(result[0])
        # payload = result[1]

        if code == 1:
            return 1, initial_tx
        else:
            # Race condition: channel or tx already exists
            return 0, None

    async def save_channel_and_initial_payword_state(
        self, channel: PaymentChannel, initial_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically save channel metadata AND the first PayWord state.
        """
        script = """
        local channel_key = KEYS[1]
        local latest_key = KEYS[2]
        local channel_json = ARGV[1]
        local state_json = ARGV[2]
        local created_ts = tonumber(ARGV[3])
        local computed_id = ARGV[4]

        if redis.call('EXISTS', channel_key) == 1 then
            return {0, ''}
        end

        if redis.call('EXISTS', latest_key) == 1 then
            return {0, ''}
        end

        redis.call('SET', channel_key, channel_json)
        redis.call('SET', latest_key, state_json)

        redis.call('ZADD', 'payment_channels:all', created_ts, computed_id)
        redis.call('ZADD', 'payment_channels:open', created_ts, computed_id)

        return {1, state_json}
        """

        channel_key = f"payment_channel:{channel.computed_id}"
        latest_key = f"payword_state:latest:{channel.computed_id}"

        channel.latest_tx = None
        channel_json = channel.model_dump_json(exclude={"latest_tx"})
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.eval(
            script,
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.computed_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        else:
            return 0, None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[PaymentChannel]:
        ids: list[str] = await self.store.zrevrange(
            "payment_channels:all", skip, skip + limit - 1
        )
        channels: List[PaymentChannel] = []
        for computed_id in ids:
            data = await self.store.get(f"payment_channel:{computed_id}")
            if data:
                channels.append(PaymentChannel.model_validate_json(data))
        return channels

    async def update(self, payment_channel: PaymentChannel) -> PaymentChannel:
        channel_key = f"payment_channel:{payment_channel.computed_id}"

        existing_raw = await self.store.get(channel_key)
        old_is_closed: Optional[bool] = None
        if existing_raw:
            existing_channel = PaymentChannel.model_validate_json(existing_raw)
            old_is_closed = existing_channel.is_closed

        await self.store.set(channel_key, payment_channel.model_dump_json())

        if old_is_closed is not None and old_is_closed != payment_channel.is_closed:
            created_ts = payment_channel.created_at.timestamp()
            if payment_channel.is_closed:
                await self.store.zrem(
                    "payment_channels:open", payment_channel.computed_id
                )
                await self.store.zadd(
                    "payment_channels:closed",
                    {payment_channel.computed_id: created_ts},
                )
            else:
                await self.store.zrem(
                    "payment_channels:closed", payment_channel.computed_id
                )
                await self.store.zadd(
                    "payment_channels:open", {payment_channel.computed_id: created_ts}
                )

        return payment_channel

    async def mark_closed(
        self,
        computed_id: str,
        close_payload_b64: Optional[str],
        client_close_signature_b64: Optional[str],
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

    async def get_paytree_state(self, computed_id: str) -> Optional[PaytreeState]:
        key = f"paytree_state:latest:{computed_id}"
        raw = await self.store.get(key)
        if not raw:
            return None
        return PaytreeState.model_validate_json(raw)

    async def save_paytree_payment(
        self, channel: PaymentChannel, new_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        """
        Atomically update the channel's latest PayTree state using Lua script.
        """
        script = """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_i = tonumber(ARGV[2])

        -- Load and decode the stored channel to read max_i (atomic validation)
        local channel_raw = redis.call('GET', channel_key)
        if not channel_raw then
            return {2, ''}
        end
        local channel = cjson.decode(channel_raw)
        local max_i = tonumber(channel.paytree_max_i)
        if not max_i then
            -- Channel exists but is missing PayTree configuration
            return {2, ''}
        end
        if new_i > max_i then
            -- i exceeds PayTree commitment window
            local current_raw = redis.call('GET', latest_key)
            return {3, current_raw or ''}
        end

        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end

        local current = cjson.decode(current_raw)
        local current_i = tonumber(current.i)
        if new_i > current_i then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
        """

        if channel.computed_id != new_state.computed_id:
            raise ValueError("Channel computed_id mismatch for PayTree payment")

        latest_key = f"paytree_state:latest:{new_state.computed_id}"
        channel_key = f"payment_channel:{new_state.computed_id}"
        payload_json = new_state.model_dump_json()

        result = await self.store.eval(
            script,
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
        self, channel: PaymentChannel, initial_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        """
        Atomically save channel metadata AND the first PayTree state.
        """
        script = """
        local channel_key = KEYS[1]
        local latest_key = KEYS[2]
        local channel_json = ARGV[1]
        local state_json = ARGV[2]
        local created_ts = tonumber(ARGV[3])
        local computed_id = ARGV[4]

        if redis.call('EXISTS', channel_key) == 1 then
            return {0, ''}
        end

        if redis.call('EXISTS', latest_key) == 1 then
            return {0, ''}
        end

        redis.call('SET', channel_key, channel_json)
        redis.call('SET', latest_key, state_json)

        redis.call('ZADD', 'payment_channels:all', created_ts, computed_id)
        redis.call('ZADD', 'payment_channels:open', created_ts, computed_id)

        return {1, state_json}
        """

        channel_key = f"payment_channel:{channel.computed_id}"
        latest_key = f"paytree_state:latest:{channel.computed_id}"

        channel.latest_tx = None
        channel_json = channel.model_dump_json(exclude={"latest_tx"})
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()

        result = await self.store.eval(
            script,
            keys=[channel_key, latest_key],
            args=[channel_json, state_json, str(created_ts), channel.computed_id],
        )

        code = int(result[0])
        if code == 1:
            return 1, initial_state
        else:
            return 0, None
