"""PayTree-specific DTOs for the issuer application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class PaytreeOpenChannelResponseDTO(BaseModel):
    """Response containing an opened PayTree-enabled channel details."""

    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int

    paytree_root_b64: str
    paytree_unit_value: int
    paytree_max_i: int
    paytree_hash_alg: str = Field("sha256")


class PaytreePaymentChannelResponseDTO(CommonSerializersMixin, BaseModel):
    """Response with PayTree-enabled payment channel details."""

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

    paytree_root_b64: str
    paytree_unit_value: int
    paytree_max_i: int
    paytree_hash_alg: str = Field("sha256")

    created_at: datetime
    closed_at: Optional[datetime] = None


class PaytreeSettlementRequestDTO(BaseModel):
    """Settlement request for PayTree mode (vendor-signed)."""

    vendor_public_key_der_b64: str
    i: int = Field(..., ge=0)
    leaf_b64: str
    siblings_b64: list[str]
    vendor_signature_b64: str
