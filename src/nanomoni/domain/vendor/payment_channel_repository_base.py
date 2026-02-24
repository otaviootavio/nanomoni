"""Base repository interface for shared payment channel operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import PaymentChannelBase


class PaymentChannelRepositoryBase(ABC):
    """Base interface for shared payment channel operations."""

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
    ) -> PaymentChannelBase:
        """Mark a payment channel as closed."""
        pass
