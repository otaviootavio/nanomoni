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


class Account(BaseModel):
    """Generic account identified by a public key with a spendable balance."""

    id: UUID = Field(default_factory=uuid4)
    public_key_der_b64: str
    balance: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()


class PaymentChannel(BaseModel):
    """Represents a unidirectional client→vendor payment channel."""

    id: UUID = Field(default_factory=uuid4)
    computed_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int = 0
    is_closed: bool = False
    closing_certificate_b64: str | None = None
    vendor_closing_signature_b64: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("closed_at")
    def serialize_closed_at(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class PaymentChannelCertificatePayload(BaseModel):
    """Signed payload for closing a payment channel."""

    computed_id: str
    amount: int


class PaymentChannelCertificate(BaseModel):
    """Certificate consisting of payload JSON and client signature."""

    payload: PaymentChannelCertificatePayload
    signature_b64: str
