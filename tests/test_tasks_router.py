"""Unit tests for task API routes."""

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.nanomoni.api.routers.tasks import router
from src.nanomoni.api.dependencies import get_task_service
from src.nanomoni.application.dtos import TaskResponseDTO


@pytest.fixture
def test_setup():
    """Set up test fixtures."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Test data
    task_id = uuid4()
    user_id = uuid4()
    task_response = TaskResponseDTO(
        id=task_id,
        title="Test Task",
        description="Test Description",
        user_id=user_id,
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        completed_at=None,
    )

    # Create mock service
    mock_service = AsyncMock()

    # Override dependency
    app.dependency_overrides[get_task_service] = lambda: mock_service

    client = TestClient(app)

    return {
        "app": app,
        "client": client,
        "task_id": task_id,
        "user_id": user_id,
        "task_response": task_response,
        "mock_service": mock_service,
    }


def test_create_task_success(test_setup):
    """Test successful task creation."""
    # Arrange
    test_setup["mock_service"].create_task.return_value = test_setup["task_response"]

    task_data = {
        "title": "Test Task",
        "description": "Test Description",
        "user_id": str(test_setup["user_id"]),
    }

    # Act
    response = test_setup["client"].post("/api/v1/tasks/", json=task_data)

    # Assert
    assert response.status_code == 201
    assert response.json()["title"] == "Test Task"
    assert response.json()["description"] == "Test Description"
    test_setup["mock_service"].create_task.assert_called_once()


def test_get_all_tasks_success(test_setup):
    """Test successful retrieval of all tasks."""
    # Arrange
    test_setup["mock_service"].get_all_tasks.return_value = [
        test_setup["task_response"]
    ]

    # Act
    response = test_setup["client"].get("/api/v1/tasks/")

    # Assert
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Test Task"
    test_setup["mock_service"].get_all_tasks.assert_called_once_with(skip=0, limit=100)


def test_get_task_by_id_success(test_setup):
    """Test successful retrieval of task by ID."""
    # Arrange
    test_setup["mock_service"].get_task_by_id.return_value = test_setup["task_response"]

    # Act
    response = test_setup["client"].get(f"/api/v1/tasks/{test_setup['task_id']}")

    # Assert
    assert response.status_code == 200
    assert response.json()["title"] == "Test Task"
    test_setup["mock_service"].get_task_by_id.assert_called_once_with(
        test_setup["task_id"]
    )


def test_update_task_success(test_setup):
    """Test successful task update."""
    # Arrange
    updated_task = TaskResponseDTO(
        id=test_setup["task_id"],
        title="Updated Task",
        description="Updated Description",
        user_id=test_setup["user_id"],
        status="running",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )

    test_setup["mock_service"].update_task.return_value = updated_task

    update_data = {"title": "Updated Task", "description": "Updated Description"}

    # Act
    response = test_setup["client"].put(
        f"/api/v1/tasks/{test_setup['task_id']}", json=update_data
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Task"
    test_setup["mock_service"].update_task.assert_called_once()


def test_delete_task_success(test_setup):
    """Test successful task deletion."""
    # Arrange
    test_setup["mock_service"].delete_task.return_value = True

    # Act
    response = test_setup["client"].delete(f"/api/v1/tasks/{test_setup['task_id']}")

    # Assert
    assert response.status_code == 204
    test_setup["mock_service"].delete_task.assert_called_once_with(
        test_setup["task_id"]
    )


def test_start_task_success(test_setup):
    """Test successful task start."""
    # Arrange
    started_task = TaskResponseDTO(
        id=test_setup["task_id"],
        title="Test Task",
        description="Test Description",
        user_id=test_setup["user_id"],
        status="running",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )

    test_setup["mock_service"].start_task.return_value = started_task

    # Act
    response = test_setup["client"].patch(
        f"/api/v1/tasks/{test_setup['task_id']}/start"
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    test_setup["mock_service"].start_task.assert_called_once_with(test_setup["task_id"])


def test_complete_task_success(test_setup):
    """Test successful task completion."""
    # Arrange
    completed_task = TaskResponseDTO(
        id=test_setup["task_id"],
        title="Test Task",
        description="Test Description",
        user_id=test_setup["user_id"],
        status="completed",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )

    test_setup["mock_service"].complete_task.return_value = completed_task

    # Act
    response = test_setup["client"].patch(
        f"/api/v1/tasks/{test_setup['task_id']}/complete"
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    test_setup["mock_service"].complete_task.assert_called_once_with(
        test_setup["task_id"]
    )


def test_get_tasks_by_user_success(test_setup):
    """Test successful retrieval of tasks by user."""
    # Arrange
    test_setup["mock_service"].get_tasks_by_user.return_value = [
        test_setup["task_response"]
    ]

    # Act
    response = test_setup["client"].get(f"/api/v1/tasks/user/{test_setup['user_id']}")

    # Assert
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Test Task"
    test_setup["mock_service"].get_tasks_by_user.assert_called_once_with(
        test_setup["user_id"], skip=0, limit=100
    )


def test_get_tasks_by_status_success(test_setup):
    """Test successful retrieval of tasks by status."""
    # Arrange
    test_setup["mock_service"].get_tasks_by_status.return_value = [
        test_setup["task_response"]
    ]

    # Act
    response = test_setup["client"].get("/api/v1/tasks/status/pending")

    # Assert
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "pending"
    test_setup["mock_service"].get_tasks_by_status.assert_called_once_with(
        "pending", skip=0, limit=100
    )
