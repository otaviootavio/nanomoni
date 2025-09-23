"""OffChainTx repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ...domain.vendor.entities import OffChainTx
from ...domain.vendor.off_chain_tx_repository import OffChainTxRepository
from ..storage import KeyValueStore


class OffChainTxRepositoryImpl(OffChainTxRepository):
    """OffChainTx repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, off_chain_tx: OffChainTx) -> OffChainTx:
        tx_key = f"off_chain_tx:{off_chain_tx.id}"
        await self.store.set(tx_key, off_chain_tx.model_dump_json())

        created_ts = off_chain_tx.created_at.timestamp()
        await self.store.zadd("off_chain_txs:all", {str(off_chain_tx.id): created_ts})
        await self.store.zadd(
            f"off_chain_txs:by_computed_id:{off_chain_tx.computed_id}",
            {str(off_chain_tx.id): created_ts},
        )

        return off_chain_tx

    async def get_by_id(self, tx_id: UUID) -> Optional[OffChainTx]:
        data = await self.store.get(f"off_chain_tx:{tx_id}")
        if not data:
            return None
        return OffChainTx.model_validate_json(data)

    async def get_by_computed_id(self, computed_id: str) -> List[OffChainTx]:
        key = f"off_chain_txs:by_computed_id:{computed_id}"
        ids: list[str] = await self.store.zrevrange(key, 0, -1)
        txs: List[OffChainTx] = []
        for tx_id in ids:
            data = await self.store.get(f"off_chain_tx:{tx_id}")
            if data:
                txs.append(OffChainTx.model_validate_json(data))
        return txs

    async def get_latest_by_computed_id(self, computed_id: str) -> Optional[OffChainTx]:
        key = f"off_chain_txs:by_computed_id:{computed_id}"
        ids: list[str] = await self.store.zrevrange(key, 0, 0)  # Get only the latest
        if not ids:
            return None

        data = await self.store.get(f"off_chain_tx:{ids[0]}")
        if not data:
            return None
        return OffChainTx.model_validate_json(data)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[OffChainTx]:
        ids: list[str] = await self.store.zrevrange(
            "off_chain_txs:all", skip, skip + limit - 1
        )
        txs: List[OffChainTx] = []
        for tx_id in ids:
            data = await self.store.get(f"off_chain_tx:{tx_id}")
            if data:
                txs.append(OffChainTx.model_validate_json(data))
        return txs

    async def update(self, off_chain_tx: OffChainTx) -> OffChainTx:
        tx_key = f"off_chain_tx:{off_chain_tx.id}"
        await self.store.set(tx_key, off_chain_tx.model_dump_json())
        return off_chain_tx

    async def delete(self, tx_id: UUID) -> bool:
        tx_key = f"off_chain_tx:{tx_id}"
        existing_raw = await self.store.get(tx_key)
        if not existing_raw:
            return False

        tx = OffChainTx.model_validate_json(existing_raw)

        await self.store.delete(tx_key)
        await self.store.zrem("off_chain_txs:all", str(tx_id))
        await self.store.zrem(
            f"off_chain_txs:by_computed_id:{tx.computed_id}", str(tx_id)
        )

        return True
