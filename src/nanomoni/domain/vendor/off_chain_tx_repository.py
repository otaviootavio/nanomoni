"""OffChainTx domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .entities import OffChainTx


class OffChainTxRepository(ABC):
    """Abstract repository interface for OffChainTx entities."""

    @abstractmethod
    async def create(self, off_chain_tx: OffChainTx) -> OffChainTx:
        """Create (or upsert) the latest off-chain transaction for a channel."""
        pass

    @abstractmethod
    async def get_by_computed_id(self, computed_id: str) -> List[OffChainTx]:
        """
        Get the latest off-chain transaction for a payment channel by computed ID
        as a single-element list (or empty if none).
        """
        pass

    @abstractmethod
    async def get_latest_by_computed_id(self, computed_id: str) -> Optional[OffChainTx]:
        """Get the latest off-chain transaction for a payment channel by computed ID."""
        pass

    @abstractmethod
    async def overwrite_latest(
        self, computed_id: str, new_off_chain_tx: OffChainTx
    ) -> OffChainTx:
        """Overwrite the latest transaction for a channel."""
        pass

    @abstractmethod
    async def delete_by_computed_id(self, computed_id: str) -> bool:
        """Delete the latest off-chain transaction for a channel, if it exists."""
        pass
