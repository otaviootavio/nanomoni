"""Vendor domain entities: User, Task, payment channel state, and PaymentChannel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer, EmailStr

from ..shared.serializers import CommonSerializersMixin, DatetimeSerializerMixin


_sentinel = object()


class User(CommonSerializersMixin, BaseModel):
    """User entity representing a system user."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    is_active: bool = True

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def update_profile(self, name: str, email: str) -> None:
        """Update user profile information."""
        self.name = name
        self.email = email
        self.updated_at = datetime.now(timezone.utc)

    def deactivate(self) -> None:
        """Deactivate the user."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def activate(self) -> None:
        """Activate the user."""
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)

    def update_details(
        self, name: Optional[str] = None, email: Optional[str] = None
    ) -> None:
        """Update user's name and/or email."""
        if name:
            self.name = name
        if email:
            self.email = email
        self.updated_at = datetime.now(timezone.utc)


class Task(CommonSerializersMixin, BaseModel):
    """Task entity representing a monitoring task."""

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    user_id: UUID
    status: str = Field(default="pending")  # pending, running, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_serializer("user_id")
    def serialize_user_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    @field_serializer("completed_at")
    def serialize_completed_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def start(self) -> None:
        """Start the task."""
        if self.status != "pending":
            raise ValueError("Task has already been started or completed.")
        self.status = "running"
        self.updated_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        """Mark task as completed."""
        if self.status == "completed":
            raise ValueError("Task is already completed.")
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def fail(self) -> None:
        """Mark task as failed."""
        if self.status == "failed":
            raise ValueError("Task is already failed.")
        self.status = "failed"
        self.updated_at = datetime.now(timezone.utc)

    def update_details(
        self,
        title: Optional[str] = None,
        description: Union[str, None, object] = _sentinel,
    ) -> None:
        """Update task's title and/or description."""
        if self.status in ["completed", "failed"]:
            raise ValueError("Cannot update a completed or failed task.")
        if title:
            self.title = title
        if description is not _sentinel:
            self.description = cast(Optional[str], description)
        self.updated_at = datetime.now(timezone.utc)


class SignatureState(DatetimeSerializerMixin, BaseModel):
    """Latest signature-mode payment state (monotonic cumulative owed amount).

    Note: we intentionally do NOT persist payload bytes. The payload can be
    deterministically reconstructed from (channel_id, cumulative_owed_amount),
    and the client signature is stored over that canonical payload.
    """

    channel_id: str = Field(..., description="Payment channel identifier")
    cumulative_owed_amount: int = Field(
        ..., ge=0, description="Cumulative amount owed to vendor"
    )
    client_signature_b64: str = Field(
        ..., description="Base64-encoded client signature"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaywordState(DatetimeSerializerMixin, BaseModel):
    """Latest PayWord payment state (monotonic counter + token)."""

    channel_id: str = Field(..., description="Payment channel identifier")
    k: int = Field(..., ge=0, description="Monotonic PayWord counter")
    token_b64: str = Field(..., description="Base64 token for this k (preimage)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaytreeState(DatetimeSerializerMixin, BaseModel):
    """Latest PayTree payment state (monotonic index + Merkle proof)."""

    channel_id: str = Field(..., description="Payment channel identifier")
    i: int = Field(..., ge=0, description="Monotonic PayTree index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(
        ..., description="List of base64-encoded sibling hashes"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaymentChannelBase(CommonSerializersMixin, BaseModel):
    """Base entity for a unidirectional client→vendor payment channel."""

    channel_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int = 0
    is_closed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None


class SignaturePaymentChannel(PaymentChannelBase):
    """Signature-mode payment channel (vendor-side cached metadata)."""

    # Vendor context: latest signature state is loaded/stored separately.
    signature_state: Optional[SignatureState] = None

    @property
    def current_balance(self) -> int:
        return (
            self.signature_state.cumulative_owed_amount if self.signature_state else 0
        )


class PaywordPaymentChannel(PaymentChannelBase):
    """PayWord-enabled payment channel with hash-chain commitment."""

    payword_root_b64: str
    payword_unit_value: int
    payword_max_k: int


class PaytreePaymentChannel(PaymentChannelBase):
    """PayTree-enabled payment channel with Merkle tree commitment."""

    paytree_root_b64: str
    paytree_unit_value: int
    paytree_max_i: int
