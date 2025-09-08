from __future__ import annotations

from ..application.use_cases import UserService, TaskService
from .vendor_api.dependencies import (
    get_user_service as _vendor_get_user_service,
    get_task_repository as _vendor_get_task_repository,
    get_user_repository as _vendor_get_user_repository,
)


def get_user_service() -> UserService:
    return _vendor_get_user_service()


def get_task_service() -> TaskService:
    task_repo = _vendor_get_task_repository()
    user_repo = _vendor_get_user_repository()
    return TaskService(task_repo, user_repo)
