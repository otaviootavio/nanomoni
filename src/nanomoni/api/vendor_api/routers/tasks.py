"""Task API routes (Vendor)."""

from __future__ import annotations

from typing import List, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ....application.vendor_dtos import CreateTaskDTO, UpdateTaskDTO, TaskResponseDTO
from ....application.vendor_use_case import TaskService
from ..dependencies import get_task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/", response_model=TaskResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: CreateTaskDTO, task_service: TaskService = Depends(get_task_service)
) -> TaskResponseDTO:
    """Create a new task."""
    try:
        return await task_service.create_task(task_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=List[TaskResponseDTO])
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    user_id: Union[UUID, None] = Query(None, description="Filter by user ID"),
    status_filter: Union[str, None] = Query(
        None, alias="status", description="Filter by task status"
    ),
    task_service: TaskService = Depends(get_task_service),
) -> List[TaskResponseDTO]:
    """Get all tasks with optional filters and pagination."""
    if user_id:
        return await task_service.get_tasks_by_user(user_id, skip=skip, limit=limit)
    elif status_filter:
        return await task_service.get_tasks_by_status(
            status_filter, skip=skip, limit=limit
        )
    else:
        return await task_service.get_all_tasks(skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskResponseDTO)
async def get_task(
    task_id: UUID, task_service: TaskService = Depends(get_task_service)
) -> TaskResponseDTO:
    """Get task by ID."""
    task = await task_service.get_task_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.put("/{task_id}", response_model=TaskResponseDTO)
async def update_task(
    task_id: UUID,
    task_data: UpdateTaskDTO,
    task_service: TaskService = Depends(get_task_service),
) -> TaskResponseDTO:
    """Update a task."""
    task = await task_service.update_task(task_id, task_data)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID, task_service: TaskService = Depends(get_task_service)
):
    """Delete a task."""
    success = await task_service.delete_task(task_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )


@router.patch("/{task_id}/start", response_model=TaskResponseDTO)
async def start_task(
    task_id: UUID, task_service: TaskService = Depends(get_task_service)
) -> TaskResponseDTO:
    """Start a task."""
    task = await task_service.start_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.patch("/{task_id}/complete", response_model=TaskResponseDTO)
async def complete_task(
    task_id: UUID, task_service: TaskService = Depends(get_task_service)
) -> TaskResponseDTO:
    """Complete a task."""
    task = await task_service.complete_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.patch("/{task_id}/fail", response_model=TaskResponseDTO)
async def fail_task(
    task_id: UUID, task_service: TaskService = Depends(get_task_service)
) -> TaskResponseDTO:
    """Mark a task as failed."""
    task = await task_service.fail_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.get("/user/{user_id}", response_model=List[TaskResponseDTO])
async def get_user_tasks(
    user_id: UUID,
    skip: int = 0,
    limit: int = 100,
    task_service: TaskService = Depends(get_task_service),
) -> List[TaskResponseDTO]:
    """Get all tasks for a specific user."""
    return await task_service.get_tasks_by_user(user_id, skip=skip, limit=limit)


@router.get("/status/{status}", response_model=List[TaskResponseDTO])
async def get_tasks_by_status(
    status: str,
    skip: int = 0,
    limit: int = 100,
    task_service: TaskService = Depends(get_task_service),
) -> List[TaskResponseDTO]:
    """Get all tasks with a specific status."""
    return await task_service.get_tasks_by_status(status, skip=skip, limit=limit)
