"""Issuer domain entities: IssuerClient and IssuerChallenge."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer


class IssuerClient(BaseModel):
    """Client registered with the issuer."""

    id: UUID = Field(default_factory=uuid4)
    public_key_der_b64: str
    balance: int = 100
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()


class IssuerChallenge(BaseModel):
    """Challenge issued to a client during registration."""

    id: UUID = Field(default_factory=uuid4)
    client_public_key_der_b64: str
    nonce_b64: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()
