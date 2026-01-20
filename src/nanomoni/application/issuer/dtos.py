"""Data Transfer Objects for the issuer application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class RegistrationRequestDTO(BaseModel):
    """Client sends only its public key (DER b64) to start registration."""

    client_public_key_der_b64: str


class RegistrationResponseDTO(BaseModel):
    """Response to registration request with client public key and initial balance."""

    client_public_key_der_b64: str
    balance: int


class IssuerPublicKeyDTO(BaseModel):
    """Issuer public key DTO."""

    der_b64: str


# Payment channel DTOs
class OpenChannelRequestDTO(BaseModel):
    """Request to open a payment channel using a client-signed envelope."""

    client_public_key_der_b64: str
    open_payload_b64: str
    open_signature_b64: str


class OpenChannelResponseDTO(BaseModel):
    """Response containing the opened channel details."""

    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int


class CloseChannelRequestDTO(BaseModel):
    """Vendor presents client-signed close envelope plus vendor's consent signature (detached) for closing."""

    channel_id: str
    close_payload_b64: str
    client_close_signature_b64: str
    vendor_close_signature_b64: str


class CloseChannelResponseDTO(BaseModel):
    """Response after closing the channel with updated balances."""

    channel_id: str
    client_balance: int
    vendor_balance: int


class GetPaymentChannelRequestDTO(BaseModel):
    """Request to get a payment channel by its channel ID."""

    channel_id: str


class PaymentChannelResponseDTO(CommonSerializersMixin, BaseModel):
    """Response with payment channel details."""

    id: UUID
    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int
    is_closed: bool
    close_payload_b64: Optional[str] = None
    client_close_signature_b64: Optional[str] = None
    vendor_close_signature_b64: Optional[str] = None
    created_at: datetime
    closed_at: Optional[datetime] = None

    # `id`, `created_at`, `closed_at` serializers provided by CommonSerializersMixin.
