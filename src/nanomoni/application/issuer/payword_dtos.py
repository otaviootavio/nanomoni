"""PayWord-specific DTOs for the issuer application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class PaywordOpenChannelResponseDTO(BaseModel):
    """Response containing an opened PayWord-enabled channel details."""

    computed_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int
    payword_hash_alg: str = Field("sha256")


class PaywordPaymentChannelResponseDTO(BaseModel):
    """Response with PayWord-enabled payment channel details."""

    id: UUID
    computed_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int
    is_closed: bool
    close_payload_b64: Optional[str] = None
    client_close_signature_b64: Optional[str] = None
    vendor_close_signature_b64: Optional[str] = None

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int
    payword_hash_alg: str = Field("sha256")

    created_at: datetime
    closed_at: Optional[datetime] = None

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("closed_at")
    def serialize_closed_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


class PaywordSettlementRequestDTO(BaseModel):
    """Settlement request for PayWord mode (vendor-signed)."""

    vendor_public_key_der_b64: str
    k: int = Field(..., ge=0)
    token_b64: str
    vendor_signature_b64: str
