"""PayWord-specific DTOs for the vendor application layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class ReceivePaywordPaymentDTO(BaseModel):
    """DTO for receiving a PayWord (hash-chain) payment."""

    k: int = Field(..., ge=0, description="Monotonic PayWord counter")
    token_b64: str = Field(..., description="Base64 token (preimage) for this k")


class PaywordPaymentResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning PayWord payment acceptance data."""

    channel_id: str
    k: int
    cumulative_owed_amount: int
    created_at: datetime
