"""Storage abstractions and Redis implementation for repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, List, Mapping, Optional, cast

import redis

from .database import DatabaseClient


class KeyValueStore(ABC):
    """Abstract key-value store with minimal operations used by repositories."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        """Get multiple keys in a single operation."""
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

    @abstractmethod
    async def eval(self, script: str, keys: List[str], args: List[str]) -> Any:
        """Execute a Lua script atomically."""
        pass

    @abstractmethod
    async def register_script(self, name: str, script: str) -> str:
        """Load script into Redis and return SHA1 hash."""
        pass

    @abstractmethod
    async def run_script(self, name: str, keys: List[str], args: List[str]) -> Any:
        """Execute script by name using cached SHA1."""
        pass


class RedisKeyValueStore(KeyValueStore):
    """Redis-backed implementation of KeyValueStore."""

    def __init__(self, db_client: DatabaseClient):
        self._db_client = db_client
        self._script_cache: dict[str, str] = {}  # name -> SHA1
        self._script_sources: dict[str, str] = {}  # name -> script text

    async def get(self, key: str) -> Optional[str]:
        async with self._db_client.get_connection() as conn:
            return await conn.get(key)

    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        """Get multiple keys in a single operation."""
        async with self._db_client.get_connection() as conn:
            return await conn.mget(keys)

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

    async def eval(self, script: str, keys: List[str], args: List[str]) -> Any:
        """Execute a Lua script atomically."""
        async with self._db_client.get_connection() as conn:
            # redis-py eval signature: script, numkeys, *keys, *args
            # Cast to ensure mypy recognizes it as awaitable
            eval_result = conn.eval(script, len(keys), *keys, *args)
            return await cast(Awaitable[Any], eval_result)

    async def register_script(self, name: str, script: str) -> str:
        """Load script into Redis and return SHA1 hash."""
        async with self._db_client.get_connection() as conn:
            sha = await conn.script_load(script)
            self._script_cache[name] = sha
            self._script_sources[name] = script
            return sha

    async def run_script(self, name: str, keys: List[str], args: List[str]) -> Any:
        """Execute script by name using cached SHA1."""
        if name not in self._script_cache:
            raise ValueError(f"Script '{name}' not registered")

        async with self._db_client.get_connection() as conn:
            try:
                evalsha_result = conn.evalsha(
                    self._script_cache[name], len(keys), *keys, *args
                )
                return await cast(Awaitable[Any], evalsha_result)
            except redis.exceptions.NoScriptError:
                # Re-register on NOSCRIPT (Redis restart)
                sha = await conn.script_load(self._script_sources[name])
                self._script_cache[name] = sha
                evalsha_result = conn.evalsha(sha, len(keys), *keys, *args)
                return await cast(Awaitable[Any], evalsha_result)
