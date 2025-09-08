"""Dependency injection for Vendor FastAPI."""

from __future__ import annotations

from functools import lru_cache

from ...envs.vendor_env import get_settings, Settings
from ...infrastructure.database import get_database_client, DatabaseClient
from ...infrastructure.vendor.repositories import (
    SQLiteUserRepository,
    SQLiteTaskRepository,
)
from ...application.vendor_use_case import UserService, TaskService


@lru_cache()
def get_settings_dependency() -> Settings:
    return get_settings()


@lru_cache()
def get_database_client_dependency() -> DatabaseClient:
    settings = get_settings_dependency()
    return get_database_client(settings)


def get_user_repository() -> SQLiteUserRepository:
    db_client = get_database_client_dependency()
    return SQLiteUserRepository(db_client)


def get_task_repository() -> SQLiteTaskRepository:
    db_client = get_database_client_dependency()
    return SQLiteTaskRepository(db_client)


def get_user_service() -> UserService:
    user_repository = get_user_repository()
    return UserService(user_repository)


def get_task_service() -> TaskService:
    task_repository = get_task_repository()
    user_repository = get_user_repository()
    return TaskService(task_repository, user_repository)
