"""OffChainTx domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from .entities import OffChainTx


class OffChainTxRepository(ABC):
    """Abstract repository interface for OffChainTx entities."""

    @abstractmethod
    async def create(self, off_chain_tx: OffChainTx) -> OffChainTx:
        """Create a new off-chain transaction."""
        pass

    @abstractmethod
    async def get_by_id(self, tx_id: UUID) -> Optional[OffChainTx]:
        """Get off-chain transaction by ID."""
        pass

    @abstractmethod
    async def get_by_computed_id(self, computed_id: str) -> List[OffChainTx]:
        """Get all off-chain transactions for a payment channel by computed ID."""
        pass

    @abstractmethod
    async def get_latest_by_computed_id(self, computed_id: str) -> Optional[OffChainTx]:
        """Get the latest off-chain transaction for a payment channel by computed ID."""
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[OffChainTx]:
        """Get all off-chain transactions with pagination."""
        pass

    @abstractmethod
    async def update(self, off_chain_tx: OffChainTx) -> OffChainTx:
        """Update an existing off-chain transaction."""
        pass

    @abstractmethod
    async def overwrite(
        self, existing_tx_id: UUID, new_off_chain_tx: OffChainTx
    ) -> OffChainTx:
        """Overwrite an existing transaction with new data, keeping the same ID."""
        pass

    @abstractmethod
    async def delete(self, tx_id: UUID) -> bool:
        """Delete an off-chain transaction."""
        pass
