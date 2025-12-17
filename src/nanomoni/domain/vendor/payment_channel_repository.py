"""Payment channel domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .entities import PaymentChannel, OffChainTx


class PaymentChannelRepository(ABC):
    """Abstract repository interface for PaymentChannel entities."""

    @abstractmethod
    async def save_channel(self, payment_channel: PaymentChannel) -> PaymentChannel:
        """Cache a new payment_channel (from issuer)."""
        pass

    @abstractmethod
    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        """Get the full channel aggregate (metadata + latest tx)."""
        pass

    @abstractmethod
    async def save_payment(
        self, channel: PaymentChannel, new_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        Atomically update the channel's latest transaction.

        Returns:
          (1, tx) -> stored (success)
          (0, tx) -> rejected (returns current tx)
          (2, None) -> payment channel missing
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_payment(
        self, channel: PaymentChannel, initial_tx: OffChainTx
    ) -> tuple[int, Optional[OffChainTx]]:
        """
        Atomically save channel metadata AND the first transaction.
        Used for the first payment flow.

        Returns:
          (1, tx) -> stored (success)
          (0, tx) -> rejected (race condition: channel/tx already exists)
        """
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[PaymentChannel]:
        """Get all payment_channels with pagination."""
        pass

    @abstractmethod
    async def update(self, payment_channel: PaymentChannel) -> PaymentChannel:
        """Update an existing payment_channel."""
        pass

    @abstractmethod
    async def mark_closed(
        self,
        computed_id: str,
        close_payload_b64: str,
        client_close_signature_b64: str,
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannel:
        """Mark a payment channel as closed, persisting close payload and signatures."""
        pass
