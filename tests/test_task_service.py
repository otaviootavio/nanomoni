"""Business logic tests for Task service."""

import unittest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.nanomoni.application.use_cases import TaskService
from src.nanomoni.application.dtos import CreateTaskDTO, UpdateTaskDTO, TaskResponseDTO
from src.nanomoni.domain.entities import Task, User


class TestTaskService(unittest.IsolatedAsyncioTestCase):
    """Test cases for TaskService business logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_task_repository = AsyncMock()
        self.mock_user_repository = AsyncMock()
        self.task_service = TaskService(
            self.mock_task_repository, self.mock_user_repository
        )

        # Test data
        self.task_id = uuid4()
        self.user_id = uuid4()

        self.user_entity = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )

        self.task_entity = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )

    async def test_create_task_success(self):
        """Test successful task creation."""
        # Arrange
        self.mock_user_repository.get_by_id.return_value = self.user_entity
        self.mock_task_repository.create.return_value = self.task_entity

        dto = CreateTaskDTO(
            title="Test Task", description="Test description", user_id=self.user_id
        )

        # Act
        result = await self.task_service.create_task(dto)

        # Assert
        self.assertIsInstance(result, TaskResponseDTO)
        self.assertEqual(result.title, "Test Task")
        self.assertEqual(result.description, "Test description")
        self.assertEqual(result.user_id, self.user_id)
        self.assertEqual(result.status, "pending")

        # Verify repository calls
        self.mock_user_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_task_repository.create.assert_called_once()

        # Verify the Task entity passed to create has correct data
        call_args = self.mock_task_repository.create.call_args[0][0]
        self.assertEqual(call_args.title, "Test Task")
        self.assertEqual(call_args.description, "Test description")
        self.assertEqual(call_args.user_id, self.user_id)

    async def test_create_task_minimal_data(self):
        """Test task creation with minimal required data."""
        # Arrange
        self.mock_user_repository.get_by_id.return_value = self.user_entity
        minimal_task = Task(
            id=self.task_id,
            title="Minimal Task",
            user_id=self.user_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.create.return_value = minimal_task

        dto = CreateTaskDTO(title="Minimal Task", user_id=self.user_id)

        # Act
        result = await self.task_service.create_task(dto)

        # Assert
        self.assertEqual(result.title, "Minimal Task")
        self.assertIsNone(result.description)
        self.assertEqual(result.user_id, self.user_id)

    async def test_create_task_user_not_found_raises_error(self):
        """Test creating task for non-existent user raises ValueError."""
        # Arrange
        self.mock_user_repository.get_by_id.return_value = None

        dto = CreateTaskDTO(title="Test Task", user_id=self.user_id)

        # Act & Assert
        with self.assertRaises(ValueError) as context:
            await self.task_service.create_task(dto)

        self.assertEqual(str(context.exception), "User not found")
        self.mock_user_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_task_repository.create.assert_not_called()

    async def test_get_task_by_id_success(self):
        """Test successful task retrieval by ID."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity

        # Act
        result = await self.task_service.get_task_by_id(self.task_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, TaskResponseDTO)
        self.assertEqual(result.id, self.task_id)
        self.assertEqual(result.title, "Test Task")
        self.assertEqual(result.user_id, self.user_id)
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)

    async def test_get_task_by_id_not_found(self):
        """Test task retrieval when task doesn't exist."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = None

        # Act
        result = await self.task_service.get_task_by_id(self.task_id)

        # Assert
        self.assertIsNone(result)
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)

    async def test_get_all_tasks_success(self):
        """Test retrieving all tasks with default pagination."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_all.return_value = tasks

        # Act
        result = await self.task_service.get_all_tasks()

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], TaskResponseDTO)
        self.assertEqual(result[0].title, "Test Task")
        self.mock_task_repository.get_all.assert_called_once_with(skip=0, limit=100)

    async def test_get_all_tasks_with_pagination(self):
        """Test retrieving all tasks with custom pagination."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_all.return_value = tasks

        # Act
        result = await self.task_service.get_all_tasks(skip=20, limit=10)

        # Assert
        self.assertEqual(len(result), 1)
        self.mock_task_repository.get_all.assert_called_once_with(skip=20, limit=10)

    async def test_get_all_tasks_empty_result(self):
        """Test retrieving all tasks when no tasks exist."""
        # Arrange
        self.mock_task_repository.get_all.return_value = []

        # Act
        result = await self.task_service.get_all_tasks()

        # Assert
        self.assertEqual(len(result), 0)

    async def test_get_tasks_by_user_success(self):
        """Test retrieving tasks by user ID."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_by_user_id.return_value = tasks

        # Act
        result = await self.task_service.get_tasks_by_user(self.user_id)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, self.user_id)
        self.mock_task_repository.get_by_user_id.assert_called_once_with(
            self.user_id, skip=0, limit=100
        )

    async def test_get_tasks_by_user_with_pagination(self):
        """Test retrieving tasks by user ID with pagination."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_by_user_id.return_value = tasks

        # Act
        result = await self.task_service.get_tasks_by_user(
            self.user_id, skip=5, limit=15
        )

        # Assert
        self.assertEqual(len(result), 1)
        self.mock_task_repository.get_by_user_id.assert_called_once_with(
            self.user_id, skip=5, limit=15
        )

    async def test_get_tasks_by_status_success(self):
        """Test retrieving tasks by status."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_by_status.return_value = tasks

        # Act
        result = await self.task_service.get_tasks_by_status("pending")

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, "pending")
        self.mock_task_repository.get_by_status.assert_called_once_with(
            "pending", skip=0, limit=100
        )

    async def test_get_tasks_by_status_with_pagination(self):
        """Test retrieving tasks by status with pagination."""
        # Arrange
        tasks = [self.task_entity]
        self.mock_task_repository.get_by_status.return_value = tasks

        # Act
        result = await self.task_service.get_tasks_by_status(
            "completed", skip=10, limit=25
        )

        # Assert
        self.assertEqual(len(result), 1)
        self.mock_task_repository.get_by_status.assert_called_once_with(
            "completed", skip=10, limit=25
        )

    async def test_update_task_success(self):
        """Test successful task update."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity

        updated_task = Task(
            id=self.task_id,
            title="Updated Task",
            description="Updated description",
            user_id=self.user_id,
            status="running",
            created_at=self.task_entity.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = updated_task

        dto = UpdateTaskDTO(
            title="Updated Task", description="Updated description", status="running"
        )

        # Act
        result = await self.task_service.update_task(self.task_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, TaskResponseDTO)
        self.assertEqual(result.title, "Updated Task")
        self.assertEqual(result.description, "Updated description")
        self.assertEqual(result.status, "running")
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)
        self.mock_task_repository.update.assert_called_once()

    async def test_update_task_not_found(self):
        """Test updating non-existent task returns None."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = None

        dto = UpdateTaskDTO(title="Updated Task")

        # Act
        result = await self.task_service.update_task(self.task_id, dto)

        # Assert
        self.assertIsNone(result)
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)
        self.mock_task_repository.update.assert_not_called()

    async def test_update_task_partial_title_only(self):
        """Test partial task update - title only."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity
        self.mock_task_repository.update.return_value = self.task_entity

        dto = UpdateTaskDTO(title="New Title")

        # Act
        result = await self.task_service.update_task(self.task_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.mock_task_repository.update.assert_called_once()

        # Verify the task entity was updated correctly
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.title, "New Title")
        self.assertEqual(updated_task_arg.description, "Test description")  # Unchanged

    async def test_update_task_partial_description_only(self):
        """Test partial task update - description only."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity
        self.mock_task_repository.update.return_value = self.task_entity

        dto = UpdateTaskDTO(description="New description")

        # Act
        result = await self.task_service.update_task(self.task_id, dto)

        # Assert
        self.assertIsNotNone(result)
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.title, "Test Task")  # Unchanged
        self.assertEqual(updated_task_arg.description, "New description")

    async def test_update_task_partial_status_only(self):
        """Test partial task update - status only."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity
        self.mock_task_repository.update.return_value = self.task_entity

        dto = UpdateTaskDTO(status="completed")

        # Act
        result = await self.task_service.update_task(self.task_id, dto)

        # Assert
        self.assertIsNotNone(result)
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.status, "completed")

    async def test_update_task_calls_update_details_method(self):
        """Test that update_task calls the entity's update_details method."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity
        self.mock_task_repository.update.return_value = self.task_entity

        dto = UpdateTaskDTO(title="New Title", description="New description")

        # Act
        await self.task_service.update_task(self.task_id, dto)

        # Assert
        # Verify update_details was called by checking updated_at is set
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertIsNotNone(updated_task_arg.updated_at)

    async def test_delete_task_success(self):
        """Test successful task deletion."""
        # Arrange
        self.mock_task_repository.delete.return_value = True

        # Act
        result = await self.task_service.delete_task(self.task_id)

        # Assert
        self.assertTrue(result)
        self.mock_task_repository.delete.assert_called_once_with(self.task_id)

    async def test_delete_task_not_found(self):
        """Test deleting non-existent task returns False."""
        # Arrange
        self.mock_task_repository.delete.return_value = False

        # Act
        result = await self.task_service.delete_task(self.task_id)

        # Assert
        self.assertFalse(result)
        self.mock_task_repository.delete.assert_called_once_with(self.task_id)

    async def test_start_task_success(self):
        """Test successful task start."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = self.task_entity

        started_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="running",
            created_at=self.task_entity.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = started_task

        # Act
        result = await self.task_service.start_task(self.task_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, TaskResponseDTO)
        self.assertEqual(result.status, "running")
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)
        self.mock_task_repository.update.assert_called_once()

        # Verify the task entity was started
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.status, "running")
        self.assertIsNotNone(updated_task_arg.updated_at)

    async def test_start_task_not_found(self):
        """Test starting non-existent task returns None."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = None

        # Act
        result = await self.task_service.start_task(self.task_id)

        # Assert
        self.assertIsNone(result)
        self.mock_task_repository.get_by_id.assert_called_once_with(self.task_id)
        self.mock_task_repository.update.assert_not_called()

    async def test_complete_task_success(self):
        """Test successful task completion."""
        # Arrange
        running_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.get_by_id.return_value = running_task

        completed_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="completed",
            created_at=running_task.created_at,
            updated_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = completed_task

        # Act
        result = await self.task_service.complete_task(self.task_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.completed_at)
        self.mock_task_repository.update.assert_called_once()

        # Verify the task entity was completed
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.status, "completed")
        self.assertIsNotNone(updated_task_arg.completed_at)

    async def test_complete_task_not_found(self):
        """Test completing non-existent task returns None."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = None

        # Act
        result = await self.task_service.complete_task(self.task_id)

        # Assert
        self.assertIsNone(result)
        self.mock_task_repository.update.assert_not_called()

    async def test_fail_task_success(self):
        """Test successful task failure."""
        # Arrange
        running_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.get_by_id.return_value = running_task

        failed_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="failed",
            created_at=running_task.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = failed_task

        # Act
        result = await self.task_service.fail_task(self.task_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.completed_at)  # Failed tasks don't get completed_at
        self.mock_task_repository.update.assert_called_once()

        # Verify the task entity was failed
        updated_task_arg = self.mock_task_repository.update.call_args[0][0]
        self.assertEqual(updated_task_arg.status, "failed")
        self.assertIsNone(updated_task_arg.completed_at)

    async def test_fail_task_not_found(self):
        """Test failing non-existent task returns None."""
        # Arrange
        self.mock_task_repository.get_by_id.return_value = None

        # Act
        result = await self.task_service.fail_task(self.task_id)

        # Assert
        self.assertIsNone(result)
        self.mock_task_repository.update.assert_not_called()

    async def test_task_status_transitions(self):
        """Test various task status transitions."""
        # Test pending -> running -> completed
        pending_task = Task(
            id=self.task_id,
            title="Test Task",
            user_id=self.user_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )

        # Start task
        self.mock_task_repository.get_by_id.return_value = pending_task
        started_task = Task(
            id=self.task_id,
            title="Test Task",
            user_id=self.user_id,
            status="running",
            created_at=pending_task.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = started_task

        result = await self.task_service.start_task(self.task_id)
        self.assertEqual(result.status, "running")

        # Complete task
        self.mock_task_repository.get_by_id.return_value = started_task
        completed_task = Task(
            id=self.task_id,
            title="Test Task",
            user_id=self.user_id,
            status="completed",
            created_at=pending_task.created_at,
            updated_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        self.mock_task_repository.update.return_value = completed_task

        result = await self.task_service.complete_task(self.task_id)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.completed_at)

    async def test_multiple_repository_interactions(self):
        """Test service methods that interact with multiple repositories."""
        # create_task interacts with both user and task repositories
        self.mock_user_repository.get_by_id.return_value = self.user_entity
        self.mock_task_repository.create.return_value = self.task_entity

        dto = CreateTaskDTO(title="Test Task", user_id=self.user_id)

        result = await self.task_service.create_task(dto)

        # Verify both repositories were called
        self.mock_user_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_task_repository.create.assert_called_once()
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
