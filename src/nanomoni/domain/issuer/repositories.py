"""Issuer domain repositories: IssuerClientRepository and IssuerChallengeRepository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from .entities import IssuerClient, Account, PaymentChannel


class IssuerClientRepository(ABC):
    """Repository for issuer-registered clients."""

    @abstractmethod
    async def create(self, client: IssuerClient) -> IssuerClient:
        pass

    @abstractmethod
    async def get_by_public_key(
        self, public_key_der_b64: str
    ) -> Optional[IssuerClient]:
        pass


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
    async def create(self, channel: PaymentChannel) -> PaymentChannel:
        pass

    @abstractmethod
    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
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
        pass
