"""PayWord domain repository interface."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from .entities import PaywordPaymentChannel, PaywordState
from .payment_channel_repository_base import PaymentChannelRepositoryBase


class PaywordRepository(PaymentChannelRepositoryBase):
    """Repository interface for PayWord payment channels."""

    @abstractmethod
    async def get_payword_state(self, channel_id: str) -> Optional[PaywordState]:
        """Get the latest PayWord state for this channel."""
        pass

    @abstractmethod
    async def get_payword_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[Optional[PaywordPaymentChannel], Optional[PaywordState]]:
        """Get PayWord channel metadata and latest state in one call."""
        pass

    @abstractmethod
    async def save_payword_payment(
        self, channel: PaywordPaymentChannel, new_state: PaywordState
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
        self, channel: PaywordPaymentChannel, initial_state: PaywordState
    ) -> tuple[int, Optional[PaywordState]]:
        """
        Atomically save channel metadata AND the first PayWord state.

        Returns:
          (1, state) -> stored (success)
          (0, None) -> rejected (race condition)
        """
        pass
