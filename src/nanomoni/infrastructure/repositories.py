"""SQLite repository implementations (adapters)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from ..domain.entities import User, Task
from ..domain.repositories import UserRepository, TaskRepository
from .database import DatabaseClient


class SQLiteUserRepository(UserRepository):
    """SQLite implementation of UserRepository."""

    def __init__(self, db_client: DatabaseClient):
        self.db_client = db_client

    async def create(self, user: User) -> User:
        """Create a new user."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (id, name, email, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    str(user.id),
                    user.name,
                    user.email,
                    user.created_at.isoformat(),
                    user.updated_at.isoformat() if user.updated_at else None,
                    user.is_active,
                ),
            )
            conn.commit()
            return user

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (str(user_id),))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_user(row)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_user(row)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users with pagination."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM users 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """,
                (limit, skip),
            )
            rows = cursor.fetchall()

            return [self._row_to_user(row) for row in rows]

    async def update(self, user: User) -> User:
        """Update an existing user."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users 
                SET name = ?, email = ?, updated_at = ?, is_active = ?
                WHERE id = ?
            """,
                (
                    user.name,
                    user.email,
                    user.updated_at.isoformat() if user.updated_at else None,
                    user.is_active,
                    str(user.id),
                ),
            )
            conn.commit()
            return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (str(user_id),))
            conn.commit()
            return cursor.rowcount > 0

    async def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE email = ?", (email,))
            return cursor.fetchone() is not None

    def _row_to_user(self, row) -> User:
        """Convert database row to User entity."""
        return User(
            id=UUID(row["id"]),
            name=row["name"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
            if row["updated_at"]
            else None,
            is_active=bool(row["is_active"]),
        )


class SQLiteTaskRepository(TaskRepository):
    """SQLite implementation of TaskRepository."""

    def __init__(self, db_client: DatabaseClient):
        self.db_client = db_client

    async def create(self, task: Task) -> Task:
        """Create a new task."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (id, title, description, user_id, status, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    str(task.id),
                    task.title,
                    task.description,
                    str(task.user_id),
                    task.status,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat() if task.updated_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                ),
            )
            conn.commit()
            return task

    async def get_by_id(self, task_id: UUID) -> Optional[Task]:
        """Get task by ID."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (str(task_id),))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_task(row)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        """Get all tasks with pagination."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """,
                (limit, skip),
            )
            rows = cursor.fetchall()

            return [self._row_to_task(row) for row in rows]

    async def get_by_user_id(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        """Get tasks by user ID."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks 
                WHERE user_id = ?
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """,
                (str(user_id), limit, skip),
            )
            rows = cursor.fetchall()

            return [self._row_to_task(row) for row in rows]

    async def get_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        """Get tasks by status."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks 
                WHERE status = ?
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """,
                (status, limit, skip),
            )
            rows = cursor.fetchall()

            return [self._row_to_task(row) for row in rows]

    async def update(self, task: Task) -> Task:
        """Update an existing task."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks 
                SET title = ?, description = ?, status = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
            """,
                (
                    task.title,
                    task.description,
                    task.status,
                    task.updated_at.isoformat() if task.updated_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    str(task.id),
                ),
            )
            conn.commit()
            return task

    async def delete(self, task_id: UUID) -> bool:
        """Delete a task."""
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (str(task_id),))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task entity."""
        return Task(
            id=UUID(row["id"]),
            title=row["title"],
            description=row["description"],
            user_id=UUID(row["user_id"]),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
            if row["updated_at"]
            else None,
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
        )
