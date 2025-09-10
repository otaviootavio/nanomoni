"""Storage abstractions and Redis implementation for repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Mapping, Optional

from .database import DatabaseClient


class KeyValueStore(ABC):
    """Abstract key-value store with minimal operations used by repositories."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> int:
        pass

    @abstractmethod
    async def zadd(self, key: str, mapping: Mapping[str, float]) -> int:
        pass

    @abstractmethod
    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        pass

    @abstractmethod
    async def zrem(self, key: str, member: str) -> int:
        pass


class RedisKeyValueStore(KeyValueStore):
    """Redis-backed implementation of KeyValueStore."""

    def __init__(self, db_client: DatabaseClient):
        self._db_client = db_client

    async def get(self, key: str) -> Optional[str]:
        async with self._db_client.get_connection() as conn:
            return await conn.get(key)

    async def set(self, key: str, value: str) -> None:
        async with self._db_client.get_connection() as conn:
            await conn.set(key, value)

    async def delete(self, key: str) -> int:
        async with self._db_client.get_connection() as conn:
            return await conn.delete(key)

    async def zadd(self, key: str, mapping: Mapping[str, float]) -> int:
        async with self._db_client.get_connection() as conn:
            return await conn.zadd(key, mapping)

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        async with self._db_client.get_connection() as conn:
            return await conn.zrevrange(key, start, end)

    async def zrem(self, key: str, member: str) -> int:
        async with self._db_client.get_connection() as conn:
            return await conn.zrem(key, member) 