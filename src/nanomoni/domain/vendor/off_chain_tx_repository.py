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

    @abstractmethod
    async def save_if_valid(self, off_chain_tx: OffChainTx) -> tuple[int, Optional[OffChainTx]]:
        """
        Atomically apply business rules and save the off-chain tx.

        Returns:
          (1, tx) -> stored (success)
          (0, tx) -> rejected because new owed_amount not greater or exceeds channel (returns current)
          (2, None) -> payment channel missing locally (caller should verify/create and retry)
        """
        pass
