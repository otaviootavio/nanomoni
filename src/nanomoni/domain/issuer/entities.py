"""Issuer domain entities: Account and PaymentChannel."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional

from pydantic import BaseModel, Field

from ..shared.serializers import CommonSerializersMixin


class Account(CommonSerializersMixin, BaseModel):
    """Generic account identified by a public key with a spendable balance."""

    id: UUID = Field(default_factory=uuid4)
    public_key_der_b64: str
    balance: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaymentChannel(CommonSerializersMixin, BaseModel):
    """Represents a unidirectional client→vendor payment channel."""

    id: UUID = Field(default_factory=uuid4)
    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int = 0
    is_closed: bool = False
    close_payload_b64: Optional[str] = None
    client_close_signature_b64: Optional[str] = None
    vendor_close_signature_b64: Optional[str] = None

    # Optional PayWord (hash-chain) commitment for PayWord-enabled channels.
    payword_root_b64: Optional[str] = None
    payword_unit_value: Optional[int] = None
    payword_max_k: Optional[int] = None
    payword_hash_alg: Optional[str] = None

    # Optional PayTree (Merkle tree) commitment for PayTree-enabled channels.
    paytree_root_b64: Optional[str] = None
    paytree_unit_value: Optional[int] = None
    paytree_max_i: Optional[int] = None
    paytree_hash_alg: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
