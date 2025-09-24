"""Task repository implementation over a storage abstraction."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ...domain.vendor.entities import Task
from ...domain.vendor.task_repository import TaskRepository
from ..storage import KeyValueStore


class TaskRepositoryImpl(TaskRepository):
    """Task repository using a KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, task: Task) -> Task:
        task_key = f"task:{task.id}"
        await self.store.set(task_key, task.model_dump_json())

        created_ts = task.created_at.timestamp()
        await self.store.zadd("tasks:all", {str(task.id): created_ts})
        await self.store.zadd(
            f"tasks:by_user:{task.user_id}", {str(task.id): created_ts}
        )
        await self.store.zadd(
            f"tasks:by_status:{task.status}", {str(task.id): created_ts}
        )
        return task

    async def get_by_id(self, task_id: UUID) -> Optional[Task]:
        data = await self.store.get(f"task:{task_id}")
        if not data:
            return None
        return Task.model_validate_json(data)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        ids: list[str] = await self.store.zrevrange("tasks:all", skip, skip + limit - 1)
        tasks: List[Task] = []
        for tid in ids:
            data = await self.store.get(f"task:{tid}")
            if data:
                tasks.append(Task.model_validate_json(data))
        return tasks

    async def get_by_user_id(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        key = f"tasks:by_user:{user_id}"
        ids: list[str] = await self.store.zrevrange(key, skip, skip + limit - 1)
        tasks: List[Task] = []
        for tid in ids:
            data = await self.store.get(f"task:{tid}")
            if data:
                tasks.append(Task.model_validate_json(data))
        return tasks

    async def get_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[Task]:
        key = f"tasks:by_status:{status}"
        ids: list[str] = await self.store.zrevrange(key, skip, skip + limit - 1)
        tasks: List[Task] = []
        for tid in ids:
            data = await self.store.get(f"task:{tid}")
            if data:
                tasks.append(Task.model_validate_json(data))
        return tasks

    async def update(self, task: Task) -> Task:
        task_key = f"task:{task.id}"
        existing_raw = await self.store.get(task_key)
        old_status: Optional[str] = None
        if existing_raw:
            existing_task = Task.model_validate_json(existing_raw)
            old_status = existing_task.status

        await self.store.set(task_key, task.model_dump_json())

        if old_status and old_status != task.status:
            await self.store.zrem(f"tasks:by_status:{old_status}", str(task.id))
            await self.store.zadd(
                f"tasks:by_status:{task.status}",
                {str(task.id): task.created_at.timestamp()},
            )
        return task

    async def delete(self, task_id: UUID) -> bool:
        task_key = f"task:{task_id}"
        existing_raw = await self.store.get(task_key)
        if not existing_raw:
            return False
        task = Task.model_validate_json(existing_raw)

        await self.store.delete(task_key)
        await self.store.zrem("tasks:all", str(task_id))
        await self.store.zrem(f"tasks:by_user:{task.user_id}", str(task_id))
        await self.store.zrem(f"tasks:by_status:{task.status}", str(task_id))
        return True
