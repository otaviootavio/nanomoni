"""Database connection and configuration."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Union
from pathlib import Path

from ..env import Settings


class DatabaseClient:
    """SQLite database client."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.database_path = self._get_database_path()

    def _get_database_path(self) -> str:
        """Get database path from settings."""
        if self.settings.database_url.startswith("sqlite:///"):
            return self.settings.database_url.replace("sqlite:///", "")
        return self.settings.database_url

    def initialize_database(self) -> None:
        """Initialize database and create tables."""
        # Ensure directory exists
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.database_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")

            # Create users table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT 1
                )
            """)

            # Create tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

            # Create indexes for better performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")

            conn.commit()

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[sqlite3.Connection, None]:
        """Get database connection with proper configuration."""
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
        finally:
            conn.close()


# Global database client instance
_db_client: Union[DatabaseClient, None] = None


def get_database_client(settings: Settings) -> DatabaseClient:
    """Get or create database client singleton."""
    global _db_client
    if _db_client is None:
        _db_client = DatabaseClient(settings)
        _db_client.initialize_database()
    return _db_client
