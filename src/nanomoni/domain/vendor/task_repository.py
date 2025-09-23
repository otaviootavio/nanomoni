"""Task domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from .entities import Task


class TaskRepository(ABC):
    """Abstract repository interface for Task entities."""

    @abstractmethod
    async def create(self, task: Task) -> Task:
        """Create a new task."""
        pass

    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Optional[Task]:
        """Get task by ID."""
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        """Get all tasks with pagination."""
        pass

    @abstractmethod
    async def get_by_user_id(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        """Get tasks by user ID."""
        pass

    @abstractmethod
    async def get_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        """Get tasks by status."""
        pass

    @abstractmethod
    async def update(self, task: Task) -> Task:
        """Update an existing task."""
        pass

    @abstractmethod
    async def delete(self, task_id: UUID) -> bool:
        """Delete a task."""
        pass
