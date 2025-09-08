"""Issuer domain repositories: IssuerClientRepository and IssuerChallengeRepository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from .entities import IssuerClient, IssuerChallenge


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


class IssuerChallengeRepository(ABC):
    """Repository for issuer registration challenges."""

    @abstractmethod
    async def create(self, challenge: IssuerChallenge) -> IssuerChallenge:
        pass

    @abstractmethod
    async def get_by_id(self, challenge_id: UUID) -> Optional[IssuerChallenge]:
        pass

    @abstractmethod
    async def delete(self, challenge_id: UUID) -> bool:
        pass
