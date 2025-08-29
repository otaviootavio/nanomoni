"""Dependency injection for FastAPI."""

from __future__ import annotations

from functools import lru_cache

from ..env import get_settings, Settings
from ..infrastructure.database import get_database_client, DatabaseClient
from ..infrastructure.repositories import SQLiteUserRepository, SQLiteTaskRepository
from ..application.use_cases import UserService, TaskService


@lru_cache()
def get_settings_dependency() -> Settings:
    """Get application settings."""
    return get_settings()


@lru_cache()
def get_database_client_dependency() -> DatabaseClient:
    """Get database client."""
    settings = get_settings_dependency()
    return get_database_client(settings)


def get_user_repository() -> SQLiteUserRepository:
    """Get user repository."""
    db_client = get_database_client_dependency()
    return SQLiteUserRepository(db_client)


def get_task_repository() -> SQLiteTaskRepository:
    """Get task repository."""
    db_client = get_database_client_dependency()
    return SQLiteTaskRepository(db_client)


def get_user_service() -> UserService:
    """Get user service."""
    user_repository = get_user_repository()
    return UserService(user_repository)


def get_task_service() -> TaskService:
    """Get task service."""
    task_repository = get_task_repository()
    user_repository = get_user_repository()
    return TaskService(task_repository, user_repository)
