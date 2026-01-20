"""Vendor domain entities: User, Task, OffChainTx, and PaymentChannel."""

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


class OffChainTx(DatetimeSerializerMixin, BaseModel):
    """Off-chain transaction entity representing the latest payment channel state."""

    channel_id: str = Field(..., description="Payment channel identifier")
    client_public_key_der_b64: str = Field(
        ..., description="Client's public key in DER format (base64)"
    )
    vendor_public_key_der_b64: str = Field(
        ..., description="Vendor's public key in DER format (base64)"
    )
    cumulative_owed_amount: int = Field(
        ..., ge=0, description="Cumulative amount owed to vendor"
    )
    payload_b64: str = Field(..., description="Base64-encoded payload")
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

    # Vendor context: latest transaction state part of the aggregate
    latest_tx: Optional[OffChainTx] = None

    @property
    def current_balance(self) -> int:
        return self.latest_tx.cumulative_owed_amount if self.latest_tx else 0
