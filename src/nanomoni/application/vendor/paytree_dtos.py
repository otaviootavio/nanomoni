"""PayTree-specific DTOs for the vendor application layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class ReceivePaytreePaymentDTO(BaseModel):
    """DTO for receiving a PayTree (Merkle proof) payment."""

    i: int = Field(..., ge=0, description="Monotonic PayTree index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(
        ..., description="List of base64-encoded sibling hashes"
    )


class PaytreePaymentResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning PayTree payment acceptance data."""

    computed_id: str
    i: int
    owed_amount: int
    created_at: datetime
