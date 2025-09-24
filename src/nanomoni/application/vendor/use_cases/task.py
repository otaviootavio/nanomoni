"""Use cases for the vendor application layer."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ....domain.vendor.entities import Task
from ....domain.vendor.task_repository import TaskRepository
from ....domain.vendor.user_repository import UserRepository
from ..dtos import (
    CreateTaskDTO,
    UpdateTaskDTO,
    TaskResponseDTO,
)


class TaskService:
    """Service for task-related operations."""

    def __init__(
        self, task_repository: TaskRepository, user_repository: UserRepository
    ):
        self.task_repository = task_repository
        self.user_repository = user_repository

    async def create_task(self, dto: CreateTaskDTO) -> TaskResponseDTO:
        """Create a new task."""
        # Verify user exists
        user = await self.user_repository.get_by_id(dto.user_id)
        if not user:
            raise ValueError("User not found")

        # Create task entity
        task = Task(title=dto.title, description=dto.description, user_id=dto.user_id)

        # Save task
        created_task = await self.task_repository.create(task)

        return TaskResponseDTO(**created_task.model_dump())

    async def get_task_by_id(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Get task by ID."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        return TaskResponseDTO(**task.model_dump())

    async def get_all_tasks(
        self, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get all tasks with pagination."""
        tasks = await self.task_repository.get_all(skip=skip, limit=limit)
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def get_tasks_by_user(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get tasks by user ID."""
        tasks = await self.task_repository.get_by_user_id(
            user_id, skip=skip, limit=limit
        )
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def get_tasks_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get tasks by status."""
        tasks = await self.task_repository.get_by_status(status, skip=skip, limit=limit)
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def update_task(
        self, task_id: UUID, dto: UpdateTaskDTO
    ) -> Optional[TaskResponseDTO]:
        """Update task details."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        # Update provided fields via entity method to set updated_at
        if dto.description is not None:
            task.update_details(title=dto.title, description=dto.description)
        else:
            task.update_details(title=dto.title)
        if dto.status is not None:
            task.status = dto.status

        updated_task = await self.task_repository.update(task)

        return TaskResponseDTO(**updated_task.model_dump())

    async def delete_task(self, task_id: UUID) -> bool:
        """Delete a task by ID."""
        return await self.task_repository.delete(task_id)

    async def start_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Start a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.start()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())

    async def complete_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Complete a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.complete()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())

    async def fail_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Fail a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.fail()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())
