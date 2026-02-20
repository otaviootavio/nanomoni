"""PayTree First Opt-specific DTOs for the vendor application layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class ReceivePaytreeFirstOptPaymentDTO(BaseModel):
    """DTO for receiving a PayTree First Opt (pruned Merkle proof) payment."""

    i: int = Field(..., ge=0, description="Monotonic PayTree index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(
        ..., description="Pruned list of base64-encoded sibling hashes"
    )


class PaytreeFirstOptPaymentResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning PayTree First Opt payment acceptance data."""

    channel_id: str
    i: int
    cumulative_owed_amount: int
    created_at: datetime
