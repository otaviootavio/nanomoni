from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PaywordOpenChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed open-channel request envelope (PayWord-enabled)."""

    model_config = ConfigDict(extra="forbid")

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int

    payword_root_b64: str = Field(
        ..., description="Base64 commitment root for the PayWord chain"
    )
    payword_unit_value: int = Field(..., gt=0, description="Value per PayWord unit")
    payword_max_k: int = Field(
        ..., gt=0, description="Maximum allowed counter (inclusive)"
    )
    payword_hash_alg: str = Field(
        "sha256", description="Hash algorithm (currently only sha256)"
    )
