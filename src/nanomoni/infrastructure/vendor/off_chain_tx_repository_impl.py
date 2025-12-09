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
