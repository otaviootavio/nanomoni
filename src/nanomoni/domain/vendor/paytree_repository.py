"""PayTree domain repository interface."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from .entities import PaytreePaymentChannel, PaytreeState
from .payment_channel_repository_base import PaymentChannelRepositoryBase


class PaytreeRepository(PaymentChannelRepositoryBase):
    """Repository interface for PayTree payment channels."""

    @abstractmethod
    async def get_paytree_state(self, channel_id: str) -> Optional[PaytreeState]:
        """Get the latest PayTree state for this channel."""
        pass

    @abstractmethod
    async def get_paytree_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaytreePaymentChannel], Optional[PaytreeState]]:
        """Get PayTree channel metadata and latest state in one call."""
        pass

    @abstractmethod
    async def save_paytree_payment(
        self, channel: PaytreePaymentChannel, new_state: PaytreeState
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
        self, channel: PaytreePaymentChannel, initial_state: PaytreeState
    ) -> tuple[int, Optional[PaytreeState]]:
        """
        Atomically save channel metadata AND the first PayTree state.

        Returns:
          (1, state) -> stored (success)
          (0, None) -> rejected (race condition)
        """
        pass
