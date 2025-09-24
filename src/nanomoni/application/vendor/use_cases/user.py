"""Use cases for the vendor application layer."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ....domain.vendor.entities import User
from ....domain.vendor.user_repository import UserRepository
from ..dtos import (
    CreateUserDTO,
    UpdateUserDTO,
    UserResponseDTO,
)


class UserService:
    """Service for user-related operations."""

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def create_user(self, dto: CreateUserDTO) -> UserResponseDTO:
        """Create a new user."""
        email = dto.email.lower()
        # Check if user already exists
        if await self.user_repository.exists_by_email(email):
            raise ValueError("User with this email already exists")

        # Create user entity
        user = User(name=dto.name, email=email)

        # Save user
        created_user = await self.user_repository.create(user)

        return UserResponseDTO(**created_user.model_dump())

    async def get_user_by_id(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Get user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        return UserResponseDTO(**user.model_dump())

    async def get_user_by_email(self, email: str) -> Optional[UserResponseDTO]:
        """Get user by email."""
        user = await self.user_repository.get_by_email(email.lower())
        if not user:
            return None

        return UserResponseDTO(**user.model_dump())

    async def get_all_users(
        self, skip: int = 0, limit: int = 100
    ) -> List[UserResponseDTO]:
        """Get all users with pagination."""
        users = await self.user_repository.get_all(skip=skip, limit=limit)
        return [UserResponseDTO(**user.model_dump()) for user in users]

    async def update_user(
        self, user_id: UUID, dto: UpdateUserDTO
    ) -> Optional[UserResponseDTO]:
        """Update user details."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        # Determine new email if provided and perform duplicate check only when changing
        new_email: Optional[str] = None
        if dto.email is not None:
            candidate = dto.email.lower()
            if candidate != user.email.lower():
                if await self.user_repository.exists_by_email(candidate):
                    raise ValueError("User with this email already exists")
            new_email = candidate

        # Use entity method to set updated_at and apply provided fields
        user.update_details(name=dto.name, email=new_email)

        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user by ID."""
        return await self.user_repository.delete(user_id)

    async def deactivate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Deactivate a user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.deactivate()
        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())

    async def activate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Activate a user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.activate()
        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())
