"""Vendor domain entities: User, Task, and OffChainTx."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer, EmailStr


_sentinel = object()


class User(BaseModel):
    """User entity representing a system user."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    is_active: bool = True

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

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

    def update_details(self, name: Optional[str] = None, email: Optional[str] = None):
        """Update user's name and/or email."""
        if name:
            self.name = name
        if email:
            self.email = email
        self.updated_at = datetime.now(timezone.utc)


class Task(BaseModel):
    """Task entity representing a monitoring task."""

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    user_id: UUID
    status: str = Field(default="pending")  # pending, running, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("user_id")
    def serialize_user_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

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
        self, title: Optional[str] = None, description: object = _sentinel
    ) -> None:
        """Update task's title and/or description."""
        if self.status in ["completed", "failed"]:
            raise ValueError("Cannot update a completed or failed task.")
        if title:
            self.title = title
        if description is not _sentinel:
            self.description = description
        self.updated_at = datetime.now(timezone.utc)


class OffChainTx(BaseModel):
    """Off-chain transaction entity representing a payment channel transaction."""

    id: UUID = Field(default_factory=uuid4)
    computed_id: str = Field(..., description="Payment channel computed ID")
    client_public_key_der_b64: str = Field(
        ..., description="Client's public key in DER format (base64)"
    )
    vendor_public_key_der_b64: str = Field(
        ..., description="Vendor's public key in DER format (base64)"
    )
    owed_amount: int = Field(..., ge=0, description="Amount owed to vendor")
    payload_b64: str = Field(..., description="Base64-encoded payload")
    signature_b64: str = Field(..., description="Base64-encoded signature")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()
