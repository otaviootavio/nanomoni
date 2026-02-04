"""Data Transfer Objects for the vendor application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from nanomoni.domain.shared.serializers import (
    CommonSerializersMixin,
    DatetimeSerializerMixin,
)


class CreateUserDTO(BaseModel):
    """DTO for creating a user."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "John Doe", "email": "john.doe@example.com"}
        }
    )

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=100)


class UpdateUserDTO(BaseModel):
    """DTO for updating a user."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = Field(None, max_length=100)


class UserResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning user data."""

    id: UUID
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: Optional[datetime]
    is_active: bool

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


class CreateTaskDTO(BaseModel):
    """DTO for creating a task."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    user_id: UUID


class UpdateTaskDTO(BaseModel):
    """DTO for updating a task."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[Literal["pending", "running", "completed", "failed"]] = Field(None)


class TaskResponseDTO(CommonSerializersMixin, BaseModel):
    """DTO for returning task data."""

    id: UUID
    title: str
    description: Optional[str]
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]

    @field_serializer("user_id")
    def serialize_user_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    @field_serializer("completed_at")
    def serialize_completed_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


class ReceivePaymentDTO(BaseModel):
    """DTO for receiving an off-chain payment."""

    channel_id: str = Field(..., description="Payment channel identifier")
    cumulative_owed_amount: int = Field(
        ..., description="Cumulative amount owed to vendor"
    )
    signature_b64: str = Field(
        ..., description="Client signature over the payment payload"
    )


class OffChainTxResponseDTO(DatetimeSerializerMixin, BaseModel):
    """DTO for returning off-chain transaction data."""

    channel_id: str
    cumulative_owed_amount: int
    created_at: datetime


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    items: list
    total: int
    skip: int
    limit: int
    has_next: bool
    has_previous: bool


class VendorPublicKeyDTO(BaseModel):
    """DTO for returning the vendor's public key in DER base64 format."""

    public_key_der_b64: str


class CloseChannelDTO(BaseModel):
    """DTO for requesting a close of a payment channel by its channel ID."""

    channel_id: str
