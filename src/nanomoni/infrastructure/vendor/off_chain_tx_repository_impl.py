"""OffChainTx repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional

from ...domain.vendor.entities import OffChainTx
from ...domain.vendor.off_chain_tx_repository import OffChainTxRepository
from ..storage import KeyValueStore


class OffChainTxRepositoryImpl(OffChainTxRepository):
    """OffChainTx repository using a KeyValueStore.

    Stores only the latest OffChainTx per payment channel, keyed by computed_id.
    """

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, off_chain_tx: OffChainTx) -> OffChainTx:
        """
        Store latest OffChainTx keyed directly by computed_id to minimise lookups.

        Keys:
          - off_chain_tx:latest:{computed_id} -> OffChainTx JSON (authoritative latest)
        """
        latest_key = f"off_chain_tx:latest:{off_chain_tx.computed_id}"
        payload_json = off_chain_tx.model_dump_json()

        await self.store.set(latest_key, payload_json)
        return off_chain_tx

    async def get_by_computed_id(self, computed_id: str) -> List[OffChainTx]:
        """
        Return the latest transaction for this channel as a single-element list,
        or an empty list if none exists.
        """
        latest = await self.get_latest_by_computed_id(computed_id)
        return [latest] if latest else []

    async def get_latest_by_computed_id(self, computed_id: str) -> Optional[OffChainTx]:
        """
        Fast-path lookup for latest tx of a channel using a dedicated key.
        """
        latest_key = f"off_chain_tx:latest:{computed_id}"
        data = await self.store.get(latest_key)
        if not data:
            return None
        return OffChainTx.model_validate_json(data)

    async def overwrite_latest(
        self, computed_id: str, new_off_chain_tx: OffChainTx
    ) -> OffChainTx:
        """
        Overwrite the latest transaction for a channel with new data.
        """
        latest_key = f"off_chain_tx:latest:{computed_id}"
        payload_json = new_off_chain_tx.model_dump_json()
        await self.store.set(latest_key, payload_json)
        return new_off_chain_tx

    async def delete_by_computed_id(self, computed_id: str) -> bool:
        """
        Delete the latest transaction for a channel, if it exists.
        """
        latest_key = f"off_chain_tx:latest:{computed_id}"
        existing_raw = await self.store.get(latest_key)
        if not existing_raw:
            return False

        await self.store.delete(latest_key)
        return True

    async def save_if_valid(
        self, off_chain_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        Use a Lua script to atomically check and update the transaction.
        Enforces business rules:
        - Channel must exist locally
        - New owed_amount <= channel.amount
        - New owed_amount > current stored owed_amount
        """
        script = """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_amount = tonumber(ARGV[2])

        local channel_raw = redis.call('GET', channel_key)
        if not channel_raw then
            return {2, ''}
        end
        
        local channel = cjson.decode(channel_raw)
        local channel_amount = tonumber(channel.amount)
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

        latest_key = f"off_chain_tx:latest:{off_chain_tx.computed_id}"
        channel_key = f"payment_channel:{off_chain_tx.computed_id}"
        payload_json = off_chain_tx.model_dump_json()

        result = await self.store.eval(
            script,
            keys=[latest_key, channel_key],
            args=[payload_json, str(off_chain_tx.owed_amount)],
        )

        # result is a list-like: [code, json_or_empty]
        code = int(result[0]) if result and result[0] is not None and result[0] != "" else 0
        payload = result[1] if len(result) > 1 and result[1] and result[1] != "" else None

        if code == 1:
            # Success: stored the new transaction
            if payload is None:
                raise RuntimeError("Unexpected: save_if_valid returned success but no payload")
            return 1, OffChainTx.model_validate_json(payload)
        elif code == 0:
            # Rejected: return current transaction (may be None if no current tx exists)
            return 0, OffChainTx.model_validate_json(payload) if payload else None
        else:
            # code == 2: channel missing
            return 2, None
