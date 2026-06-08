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
    optimization_type: int = Field(
        default=0,
        ge=0,
        le=1,
        description="0=standard (full proof), 1=first-opt (pruned proof)",
    )
    paytree_max_i: int = Field(
        default=0,
        ge=0,
        description="Required for first-opt: max leaf index from channel (to compute node keys)",
    )


class PaytreePaymentResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning PayTree payment acceptance data."""

    channel_id: str
    i: int
    cumulative_owed_amount: int
    created_at: datetime
