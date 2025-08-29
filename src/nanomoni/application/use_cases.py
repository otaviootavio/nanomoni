"""Use cases for the application layer."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ..domain.entities import User, Task, _sentinel
from ..domain.repositories import UserRepository, TaskRepository
from .dtos import (
    CreateUserDTO,
    UpdateUserDTO,
    UserResponseDTO,
    CreateTaskDTO,
    UpdateTaskDTO,
    TaskResponseDTO,
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
        """Update a user."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        # Check if email is being changed and if it already exists
        if dto.email:
            new_email = dto.email.lower()
            if new_email != user.email:
                if await self.user_repository.exists_by_email(new_email):
                    raise ValueError("User with this email already exists")
                user.email = new_email

        # Update user's name if provided
        if dto.name:
            user.name = dto.name

        # Call update_profile to set updated_at and persist changes
        user.update_profile(user.name, user.email)

        updated_user = await self.user_repository.update(user)
        return UserResponseDTO(**updated_user.model_dump())

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user."""
        return await self.user_repository.delete(user_id)

    async def deactivate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Deactivate a user."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.deactivate()
        updated_user = await self.user_repository.update(user)
        return UserResponseDTO(**updated_user.model_dump())

    async def activate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Activate a user."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.activate()
        updated_user = await self.user_repository.update(user)
        return UserResponseDTO(**updated_user.model_dump())


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
        """Update a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        update_data = dto.model_dump(exclude_unset=True)

        # Handle detail updates
        if "title" in update_data or "description" in update_data:
            description = (
                update_data.get("description")
                if "description" in update_data
                else _sentinel
            )
            task.update_details(
                title=update_data.get("title"),
                description=description,
            )

        # Handle status changes
        if "status" in update_data:
            new_status = update_data["status"]
            if new_status == "running":
                task.start()
            elif new_status == "completed":
                task.complete()
            elif new_status == "failed":
                task.fail()
            elif new_status == "pending":
                task.reset()
            else:
                # This should not be reachable due to DTO validation
                raise ValueError(f"Invalid task status: {new_status}")

        updated_task = await self.task_repository.update(task)
        return TaskResponseDTO(**updated_task.model_dump())

    async def delete_task(self, task_id: UUID) -> bool:
        """Delete a task."""
        return await self.task_repository.delete(task_id)

    async def start_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Start a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        task.start()
        updated_task = await self.task_repository.update(task)
        return TaskResponseDTO(**updated_task.model_dump())

    async def complete_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Complete a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        task.complete()
        updated_task = await self.task_repository.update(task)
        return TaskResponseDTO(**updated_task.model_dump())

    async def fail_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Mark a task as failed."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        task.fail()
        updated_task = await self.task_repository.update(task)
        return TaskResponseDTO(**updated_task.model_dump())
