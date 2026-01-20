"""Payment channel domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import (
    PaymentChannelBase,
    PaytreePaymentChannel,
    PaytreeState,
    PaywordPaymentChannel,
    PaywordState,
    SignatureState,
    SignaturePaymentChannel,
)


class PaymentChannelRepository(ABC):
    """Abstract repository interface for PaymentChannel entities."""

    @abstractmethod
    async def save_channel(
        self, payment_channel: PaymentChannelBase
    ) -> PaymentChannelBase:
        """Cache a new payment_channel (from issuer)."""
        pass

    @abstractmethod
    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannelBase]:
        """Get the full channel aggregate (metadata + latest tx)."""
        pass

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

    @abstractmethod
    async def get_all(
        self, skip: int = 0, limit: int = 100
    ) -> list[PaymentChannelBase]:
        """Get all payment_channels with pagination."""
        pass

    @abstractmethod
    async def update(self, payment_channel: PaymentChannelBase) -> PaymentChannelBase:
        """Update an existing payment_channel."""
        pass

    @abstractmethod
    async def mark_closed(
        self,
        channel_id: str,
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannelBase:
        """Mark a payment channel as closed."""
        pass
