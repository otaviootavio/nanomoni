"""Database connection and configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Union, Protocol, Optional

import redis.asyncio as redis


class HasDatabaseSettings(Protocol):
    database_url: str


class DatabaseClient:
    """Redis database client (replaces SQLite)."""

    def __init__(self, settings: HasDatabaseSettings):
        self.settings = settings
        self._redis: Optional[redis.Redis] = None

    def initialize_database(self) -> None:
        """Initialize Redis connection instance. No schema to create."""
        # Expecting URL like: redis://host:port/0
        self._redis = redis.from_url(self.settings.database_url, decode_responses=True)

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[redis.Redis, None]:
        """Yield a Redis connection (async client)."""
        if self._redis is None:
            self.initialize_database()
        assert self._redis is not None
        try:
            yield self._redis
        finally:
            # Keep pooled connection alive; do not close here
            pass


# Global database client instance
_db_client: Union[DatabaseClient, None] = None


def get_database_client(settings: HasDatabaseSettings) -> DatabaseClient:
    """Get or create database client singleton."""
    global _db_client
    if _db_client is None:
        _db_client = DatabaseClient(settings)
    return _db_client
