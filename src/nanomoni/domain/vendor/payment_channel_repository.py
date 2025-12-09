"""Payment channel domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .entities import PaymentChannel


class PaymentChannelRepository(ABC):
    """Abstract repository interface for PaymentChannel entities."""

    @abstractmethod
    async def create(self, payment_channel: PaymentChannel) -> PaymentChannel:
        """Create a new payment_channel."""
        pass

    @abstractmethod
    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        """Get payment_channel by computed_id."""
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
