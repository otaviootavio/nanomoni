"""Issuer repositories implemented over a storage abstraction."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from ...domain.issuer.entities import IssuerClient, IssuerChallenge
from ...domain.issuer.repositories import (
    IssuerClientRepository,
    IssuerChallengeRepository,
)
from ..storage import KeyValueStore


class IssuerClientRepositoryImpl(IssuerClientRepository):
    """Issuer client repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, client: IssuerClient) -> IssuerClient:
        pk_key = f"issuer_client:pk:{client.public_key_der_b64}"
        existing = await self.store.get(pk_key)
        if existing is not None:
            raise ValueError("Client with this public key already exists")

        client_key = f"issuer_client:{client.id}"
        await self.store.set(client_key, client.model_dump_json())
        await self.store.set(pk_key, str(client.id))
        return client

    async def get_by_public_key(
        self, public_key_der_b64: str
    ) -> Optional[IssuerClient]:
        pk_key = f"issuer_client:pk:{public_key_der_b64}"
        client_id = await self.store.get(pk_key)
        if not client_id:
            return None
        data = await self.store.get(f"issuer_client:{client_id}")
        if not data:
            return None
        return IssuerClient.model_validate_json(data)


class IssuerChallengeRepositoryImpl(IssuerChallengeRepository):
    """Issuer challenge repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, challenge: IssuerChallenge) -> IssuerChallenge:
        key = f"issuer_challenge:{challenge.id}"
        await self.store.set(key, challenge.model_dump_json())
        return challenge

    async def get_by_id(self, challenge_id: UUID) -> Optional[IssuerChallenge]:
        data = await self.store.get(f"issuer_challenge:{challenge_id}")
        if not data:
            return None
        return IssuerChallenge.model_validate_json(data)

    async def delete(self, challenge_id: UUID) -> bool:
        res = await self.store.delete(f"issuer_challenge:{challenge_id}")
        return res == 1
