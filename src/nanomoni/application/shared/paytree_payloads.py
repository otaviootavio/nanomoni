"""PayTree-specific payloads for channel opening."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PaytreeOpenChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed open-channel request envelope (PayTree-enabled)."""

    model_config = ConfigDict(extra="forbid")

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int

    paytree_root_b64: str = Field(
        ..., description="Base64 commitment root for the PayTree Merkle tree"
    )
    paytree_unit_value: int = Field(..., gt=0, description="Value per PayTree unit")
    paytree_max_i: int = Field(
        ...,
        ge=0,
        description="Maximum allowed index (inclusive, tree has max_i+1 leaves)",
    )


class PaytreeSettlementPayload(BaseModel):
    """Payload signed by the vendor when settling a PayTree channel on the issuer."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    i: int = Field(..., ge=0)
    leaf_b64: str
    siblings_b64: list[str]


class PaytreeChildPairSettlementPayload(BaseModel):
    """Payload signed by the vendor when settling a PayTree child-pair channel.

    Unlike the standard/first-opt settlement (full leaf->root proof), this
    carries a frontier proof: the most recently paid node's children plus one
    outer sibling per remaining level up to the root (see
    `protocol.paytree_child_pair.verify_close_proof`).
    """

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    k: int = Field(..., ge=1)
    left_b64: str
    right_b64: str
    siblings_b64: list[str]
