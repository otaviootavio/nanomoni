"""In-memory implementation of KeyValueStore for testing, backed by fakeredis."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import fakeredis

from nanomoni.infrastructure.storage import RedisKeyValueStore


class _FakeDatabaseClient:
    """Minimal DatabaseClient shim yielding a fakeredis connection."""

    def __init__(self, client: fakeredis.FakeAsyncRedis) -> None:
        self._client = client

    @asynccontextmanager
    async def get_connection(
        self,
    ) -> AsyncGenerator[fakeredis.FakeAsyncRedis, None]:
        yield self._client


class InMemoryKeyValueStore(RedisKeyValueStore):
    """KeyValueStore backed by an isolated fakeredis server, for fast testing.

    Reuses RedisKeyValueStore's logic unmodified against a fakeredis.FakeAsyncRedis
    client, so the real Lua scripts in infrastructure/scripts.py execute via
    fakeredis's embedded Lua interpreter instead of being hand-reimplemented
    in Python.
    """

    def __init__(self) -> None:
        self._fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
        super().__init__(_FakeDatabaseClient(self._fake_client))  # type: ignore[arg-type]

    async def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        await self._fake_client.flushall()
