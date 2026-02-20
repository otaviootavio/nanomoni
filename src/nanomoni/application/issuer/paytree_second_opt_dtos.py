"""PayTree Second Opt-specific DTOs for the issuer application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class PaytreeSecondOptOpenChannelResponseDTO(BaseModel):
    """Response containing an opened PayTree Second Opt-enabled channel details."""

    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int

    paytree_second_opt_root_b64: str
    paytree_second_opt_unit_value: int
    paytree_second_opt_max_i: int


class PaytreeSecondOptPaymentChannelResponseDTO(CommonSerializersMixin, BaseModel):
    """Response with PayTree Second Opt-enabled payment channel details."""

    id: UUID
    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int
    is_closed: bool
    vendor_close_signature_b64: Optional[str] = None

    paytree_second_opt_root_b64: str
    paytree_second_opt_unit_value: int
    paytree_second_opt_max_i: int

    created_at: datetime
    closed_at: Optional[datetime] = None


class PaytreeSecondOptSettlementRequestDTO(BaseModel):
    """Settlement request for PayTree Second Opt mode (vendor-signed)."""

    vendor_public_key_der_b64: str
    i: int = Field(..., ge=0)
    leaf_b64: str
    siblings_b64: list[str]
    vendor_signature_b64: str
