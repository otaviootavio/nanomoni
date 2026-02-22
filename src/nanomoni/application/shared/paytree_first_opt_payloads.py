"""PayTree First Opt-specific payloads for channel opening and settlement."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PaytreeFirstOptOpenChannelRequestPayload(BaseModel):
    """Payload carried by client-signed open-channel request (PayTree First Opt)."""

    model_config = ConfigDict(extra="forbid")

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int

    paytree_first_opt_root_b64: str = Field(
        ..., description="Base64 commitment root for the PayTree First Opt Merkle tree"
    )
    paytree_first_opt_unit_value: int = Field(
        ..., gt=0, description="Value per PayTree First Opt unit"
    )
    paytree_first_opt_max_i: int = Field(
        ...,
        ge=0,
        description="Maximum allowed index (inclusive, tree has max_i+1 leaves)",
    )


class PaytreeFirstOptSettlementPayload(BaseModel):
    """Payload signed by vendor when settling a PayTree First Opt channel."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    i: int = Field(..., ge=0)
    leaf_b64: str
    siblings_b64: list[str]
