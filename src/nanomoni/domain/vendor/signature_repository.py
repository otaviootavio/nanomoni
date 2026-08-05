"""Signature payment domain repository interface."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from .entities import SignaturePaymentChannel, SignatureState
from .payment_channel_repository_base import PaymentChannelRepositoryBase


class SignatureRepository(PaymentChannelRepositoryBase):
    """Repository interface for signature-based payment channels."""

    @abstractmethod
    async def save_payment(
        self, channel: SignaturePaymentChannel, new_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        """
        Atomically update the channel's latest signature state.

        Returns:
          (1, state) -> stored (success)
          (0, state) -> rejected (returns current state)
          (2, None) -> payment channel missing
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_payment(
        self, channel: SignaturePaymentChannel, initial_state: SignatureState
    ) -> tuple[int, Optional[SignatureState]]:
        """
        Atomically save channel metadata AND the first signature state.
        Used for the first payment flow.

        Returns:
          (1, state) -> stored (success)
          (0, state) -> rejected (race condition: channel/state already exists)
        """
        pass
