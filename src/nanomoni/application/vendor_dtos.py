"""Data Transfer Objects for the vendor application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_serializer


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


class UserResponseDTO(BaseModel):
    """DTO for returning user data."""

    id: UUID
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: Optional[datetime]
    is_active: bool

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

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


class TaskResponseDTO(BaseModel):
    """DTO for returning task data."""

    id: UUID
    title: str
    description: Optional[str]
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]

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


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    items: list
    total: int
    skip: int
    limit: int
    has_next: bool
    has_previous: bool
