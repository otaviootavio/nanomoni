"""Shared Pydantic serializers used across DTOs/entities."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import field_serializer


class DatetimeSerializerMixin:
    """Serialize common datetime fields consistently."""

    @field_serializer("created_at", check_fields=False)
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()


class CommonSerializersMixin(DatetimeSerializerMixin):
    """Common field serializers shared across multiple models.

    Uses `check_fields=False` so the mixin can be used by models that don't
    declare all fields (e.g., some models may have `created_at` but not `id`).
    """

    @field_serializer("id", check_fields=False)
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    @field_serializer("closed_at", check_fields=False)
    def serialize_closed_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
