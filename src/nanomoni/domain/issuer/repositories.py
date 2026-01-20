"""Issuer domain repositories: AccountRepository and PaymentChannelRepository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import Account, PaymentChannelBase


class AccountRepository(ABC):
    """Repository for generic accounts (client and vendor)."""

    @abstractmethod
    async def upsert(self, account: Account) -> Account:
        pass

    @abstractmethod
    async def get_by_public_key(self, public_key_der_b64: str) -> Optional[Account]:
        pass

    @abstractmethod
    async def update_balance(self, public_key_der_b64: str, delta: int) -> Account:
        """Atomically adjust balance by delta (can be negative)."""
        pass


class PaymentChannelRepository(ABC):
    """Repository for payment channels."""

    @abstractmethod
    async def create(self, channel: PaymentChannelBase) -> PaymentChannelBase:
        pass

    @abstractmethod
    async def get_by_channel_id(self, channel_id: str) -> Optional[PaymentChannelBase]:
        pass

    @abstractmethod
    async def delete_by_channel_id(self, channel_id: str) -> int:
        """Delete channel by channel_id. Returns number of deleted keys."""
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
    ) -> PaymentChannelBase:
        pass
