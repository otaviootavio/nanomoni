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


class PaymentChannelBase(CommonSerializersMixin, BaseModel):
    """Base entity for a unidirectional client→vendor payment channel."""

    id: UUID = Field(default_factory=uuid4)
    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int = 0
    is_closed: bool = False
    vendor_close_signature_b64: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None


class SignaturePaymentChannel(PaymentChannelBase):
    """Signature-mode payment channel with close payload and client signature."""

    close_payload_b64: Optional[str] = None
    client_close_signature_b64: Optional[str] = None


class PaywordPaymentChannel(PaymentChannelBase):
    """PayWord-enabled payment channel with hash-chain commitment."""

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int
    payword_hash_alg: str = "sha256"


class PaytreePaymentChannel(PaymentChannelBase):
    """PayTree-enabled payment channel with Merkle tree commitment."""

    paytree_root_b64: str
    paytree_unit_value: int
    paytree_max_i: int
    paytree_hash_alg: str = "sha256"
