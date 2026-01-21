"""PayWord-specific DTOs for the issuer application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class PaywordOpenChannelResponseDTO(BaseModel):
    """Response containing an opened PayWord-enabled channel details."""

    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int


class PaywordPaymentChannelResponseDTO(CommonSerializersMixin, BaseModel):
    """Response with PayWord-enabled payment channel details."""

    id: UUID
    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int
    is_closed: bool
    vendor_close_signature_b64: Optional[str] = None

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int

    created_at: datetime
    closed_at: Optional[datetime] = None


class PaywordSettlementRequestDTO(BaseModel):
    """Settlement request for PayWord mode (vendor-signed)."""

    vendor_public_key_der_b64: str
    k: int = Field(..., ge=0)
    token_b64: str
    vendor_signature_b64: str
