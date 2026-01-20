"""Payment channel domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .entities import PaymentChannel, OffChainTx, PaywordState, PaytreeState


class PaymentChannelRepository(ABC):
    """Abstract repository interface for PaymentChannel entities."""

    @abstractmethod
    async def save_channel(self, payment_channel: PaymentChannel) -> PaymentChannel:
        """Cache a new payment_channel (from issuer)."""
        pass

    @abstractmethod
    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannel]:
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
    async def get_payword_state(self, channel_id: str) -> Optional[PaywordState]:
        """Get the latest PayWord state for this channel."""
        pass

    @abstractmethod
    async def save_payword_payment(
        self, channel: PaymentChannel, new_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically update the channel's latest PayWord state.

        Returns:
          (1, state) -> stored (success)
          (0, state) -> rejected (returns current state)
          (2, None) -> payment channel missing
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_payword_state(
        self, channel: PaymentChannel, initial_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically save channel metadata AND the first PayWord state.

        Returns:
          (1, state) -> stored (success)
          (0, None) -> rejected (race condition)
        """
        pass

    @abstractmethod
    async def get_paytree_state(self, channel_id: str) -> Optional[PaytreeState]:
        """Get the latest PayTree state for this channel."""
        pass

    @abstractmethod
    async def save_paytree_payment(
        self, channel: PaymentChannel, new_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        """
        Atomically update the channel's latest PayTree state.

        Returns:
          (1, state) -> stored (success)
          (0, state) -> rejected (returns current state)
          (2, None) -> payment channel missing
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_paytree_state(
        self, channel: PaymentChannel, initial_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        """
        Atomically save channel metadata AND the first PayTree state.

        Returns:
          (1, state) -> stored (success)
          (0, None) -> rejected (race condition)
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
        channel_id: str,
        close_payload_b64: Optional[str],
        client_close_signature_b64: Optional[str],
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannel:
        """Mark a payment channel as closed, persisting close payload and signatures."""
        pass
