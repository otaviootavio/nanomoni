"""User repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ...domain.vendor.entities import User
from ...domain.vendor.user_repository import UserRepository
from ..storage import KeyValueStore


class UserRepositoryImpl(UserRepository):
    """User repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, user: User) -> User:
        email_key = f"user:email:{user.email}"
        existing = await self.store.get(email_key)
        if existing is not None:
            raise ValueError("Email already exists")

        user_key = f"user:{user.id}"
        await self.store.set(user_key, user.model_dump_json())

        created_ts = user.created_at.timestamp()
        await self.store.zadd("users:all", {str(user.id): created_ts})
        await self.store.set(email_key, str(user.id))
        return user

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        user_key = f"user:{user_id}"
        data = await self.store.get(user_key)
        if not data:
            return None
        return User.model_validate_json(data)

    async def get_by_email(self, email: str) -> Optional[User]:
        email_key = f"user:email:{email}"
        user_id = await self.store.get(email_key)
        if not user_id:
            return None
        data = await self.store.get(f"user:{user_id}")
        if not data:
            return None
        return User.model_validate_json(data)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        ids: list[str] = await self.store.zrevrange("users:all", skip, skip + limit - 1)
        users: List[User] = []
        for user_id in ids:
            data = await self.store.get(f"user:{user_id}")
            if data:
                users.append(User.model_validate_json(data))
        return users

    async def update(self, user: User) -> User:
        user_key = f"user:{user.id}"
        existing_raw = await self.store.get(user_key)
        old_email: Optional[str] = None
        if existing_raw:
            existing_user = User.model_validate_json(existing_raw)
            old_email = str(existing_user.email)

        await self.store.set(user_key, user.model_dump_json())

        if old_email and old_email != str(user.email):
            await self.store.delete(f"user:email:{old_email}")
            await self.store.set(f"user:email:{user.email}", str(user.id))
        return user

    async def delete(self, user_id: UUID) -> bool:
        user_key = f"user:{user_id}"
        existing_raw = await self.store.get(user_key)
        if not existing_raw:
            return False
        user = User.model_validate_json(existing_raw)

        await self.store.delete(user_key)
        await self.store.delete(f"user:email:{user.email}")
        await self.store.zrem("users:all", str(user_id))
        return True

    async def exists_by_email(self, email: str) -> bool:
        return (await self.store.get(f"user:email:{email}")) is not None
