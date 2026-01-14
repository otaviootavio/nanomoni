"""PayWord-specific DTOs for the vendor application layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer


class ReceivePaywordPaymentDTO(BaseModel):
    """DTO for receiving a PayWord (hash-chain) payment."""

    k: int = Field(..., ge=0, description="Monotonic PayWord counter")
    token_b64: str = Field(..., description="Base64 token (preimage) for this k")


class PaywordPaymentResponseDTO(BaseModel):
    """DTO for returning PayWord payment acceptance data."""

    computed_id: str
    k: int
    owed_amount: int
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()
