"""PayTree-specific DTOs for the vendor application layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nanomoni.domain.shared.serializers import CommonSerializersMixin


class ReceivePaytreeStdPaymentDTO(BaseModel):
    """DTO for receiving a standard (full-proof) PayTree payment."""

    i: int = Field(..., ge=0, description="Monotonic PayTree index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(..., description="Base64-encoded sibling hashes")


class ReceivePaytreeFirstOptPaymentDTO(BaseModel):
    """DTO for receiving a first-opt (pruned-proof) PayTree payment."""

    i: int = Field(..., ge=0, description="Monotonic PayTree index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(..., description="Base64-encoded sibling hashes")
    paytree_max_i: int = Field(
        ..., gt=0, description="Channel max_i (needed to compute node keys)"
    )


class PaytreePaymentResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning PayTree payment acceptance data."""

    channel_id: str
    i: int
    cumulative_owed_amount: int
    created_at: datetime
