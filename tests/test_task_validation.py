"""Validation tests for Task feature - DTOs and Entities."""

import unittest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from src.nanomoni.application.dtos import CreateTaskDTO, UpdateTaskDTO, TaskResponseDTO
from src.nanomoni.domain.entities import Task


class TestTaskDTOValidation(unittest.TestCase):
    """Test cases for Task DTO validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.user_id = uuid4()

    def test_create_task_dto_valid_data(self):
        """Test CreateTaskDTO with valid data."""
        # Act
        dto = CreateTaskDTO(
            title="Test Task", description="This is a test task", user_id=self.user_id
        )

        # Assert
        self.assertEqual(dto.title, "Test Task")
        self.assertEqual(dto.description, "This is a test task")
        self.assertEqual(dto.user_id, self.user_id)

    def test_create_task_dto_minimal_valid_data(self):
        """Test CreateTaskDTO with minimal required data."""
        # Act
        dto = CreateTaskDTO(title="Test Task", user_id=self.user_id)

        # Assert
        self.assertEqual(dto.title, "Test Task")
        self.assertIsNone(dto.description)
        self.assertEqual(dto.user_id, self.user_id)

    def test_create_task_dto_title_validation(self):
        """Test CreateTaskDTO title field validation."""
        # Empty title
        with self.assertRaises(ValidationError) as context:
            CreateTaskDTO(title="", user_id=self.user_id)

        errors = context.exception.errors()
        self.assertTrue(any("title" in str(error).lower() for error in errors))

        # Title too long (over 200 characters)
        long_title = "a" * 201
        with self.assertRaises(ValidationError) as context:
            CreateTaskDTO(title=long_title, user_id=self.user_id)

        errors = context.exception.errors()
        self.assertTrue(any("title" in str(error).lower() for error in errors))

        # Valid title at boundary (exactly 200 characters)
        boundary_title = "a" * 200
        dto = CreateTaskDTO(title=boundary_title, user_id=self.user_id)
        self.assertEqual(dto.title, boundary_title)

    def test_create_task_dto_description_validation(self):
        """Test CreateTaskDTO description field validation."""
        # Description too long (over 1000 characters)
        long_description = "a" * 1001
        with self.assertRaises(ValidationError) as context:
            CreateTaskDTO(
                title="Test Task", description=long_description, user_id=self.user_id
            )

        errors = context.exception.errors()
        self.assertTrue(any("description" in str(error).lower() for error in errors))

        # Valid description at boundary (exactly 1000 characters)
        boundary_description = "a" * 1000
        dto = CreateTaskDTO(
            title="Test Task", description=boundary_description, user_id=self.user_id
        )
        self.assertEqual(dto.description, boundary_description)

        # None description should be valid
        dto_no_desc = CreateTaskDTO(title="Test Task", user_id=self.user_id)
        self.assertIsNone(dto_no_desc.description)

    def test_create_task_dto_missing_required_fields(self):
        """Test CreateTaskDTO with missing required fields."""
        # Missing title
        with self.assertRaises(ValidationError):
            CreateTaskDTO(user_id=self.user_id)

        # Missing user_id
        with self.assertRaises(ValidationError):
            CreateTaskDTO(title="Test Task")

        # Missing both
        with self.assertRaises(ValidationError):
            CreateTaskDTO()

    def test_update_task_dto_valid_data(self):
        """Test UpdateTaskDTO with valid data."""
        # Full update
        dto = UpdateTaskDTO(
            title="Updated Task", description="Updated description", status="completed"
        )
        self.assertEqual(dto.title, "Updated Task")
        self.assertEqual(dto.description, "Updated description")
        self.assertEqual(dto.status, "completed")

        # Partial updates
        dto_title_only = UpdateTaskDTO(title="Updated Task")
        self.assertEqual(dto_title_only.title, "Updated Task")
        self.assertIsNone(dto_title_only.description)
        self.assertIsNone(dto_title_only.status)

        dto_status_only = UpdateTaskDTO(status="running")
        self.assertIsNone(dto_status_only.title)
        self.assertIsNone(dto_status_only.description)
        self.assertEqual(dto_status_only.status, "running")

        # Empty update (all optional)
        dto_empty = UpdateTaskDTO()
        self.assertIsNone(dto_empty.title)
        self.assertIsNone(dto_empty.description)
        self.assertIsNone(dto_empty.status)

    def test_update_task_dto_status_validation(self):
        """Test UpdateTaskDTO status field validation."""
        valid_statuses = ["pending", "running", "completed", "failed"]

        # Test valid statuses
        for status in valid_statuses:
            with self.subTest(status=status):
                dto = UpdateTaskDTO(status=status)
                self.assertEqual(dto.status, status)

        # Test invalid statuses
        invalid_statuses = ["invalid", "PENDING", "Complete", "unknown", ""]

        for status in invalid_statuses:
            with self.subTest(status=status):
                with self.assertRaises(ValidationError) as context:
                    UpdateTaskDTO(status=status)

                errors = context.exception.errors()
                self.assertTrue(any("status" in str(error).lower() for error in errors))

    def test_update_task_dto_validation_when_provided(self):
        """Test UpdateTaskDTO validation when fields are provided."""
        # Empty title when provided
        with self.assertRaises(ValidationError) as context:
            UpdateTaskDTO(title="")

        errors = context.exception.errors()
        self.assertTrue(any("title" in str(error).lower() for error in errors))

        # Title too long when provided
        long_title = "a" * 201
        with self.assertRaises(ValidationError):
            UpdateTaskDTO(title=long_title)

        # Description too long when provided
        long_description = "a" * 1001
        with self.assertRaises(ValidationError):
            UpdateTaskDTO(description=long_description)

    def test_update_task_dto_description_none_vs_empty(self):
        """Test UpdateTaskDTO handles None vs empty string for description."""
        # None description (field not provided)
        dto_none = UpdateTaskDTO(title="Test")
        self.assertIsNone(dto_none.description)

        # Empty description (explicitly clearing)
        dto_empty = UpdateTaskDTO(title="Test", description="")
        self.assertEqual(dto_empty.description, "")

    def test_task_response_dto_serialization(self):
        """Test TaskResponseDTO serialization and validation."""
        task_id = uuid4()
        user_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)

        # Full response DTO
        dto = TaskResponseDTO(
            id=task_id,
            title="Test Task",
            description="Test description",
            user_id=user_id,
            status="completed",
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
        )

        # Test serialization
        data = dto.model_dump()
        self.assertEqual(data["id"], str(task_id))
        self.assertEqual(data["user_id"], str(user_id))
        self.assertEqual(data["title"], "Test Task")
        self.assertEqual(data["description"], "Test description")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["created_at"], created_at.isoformat())
        self.assertEqual(data["updated_at"], updated_at.isoformat())
        self.assertEqual(data["completed_at"], completed_at.isoformat())

        # Test with None optional fields
        dto_minimal = TaskResponseDTO(
            id=task_id,
            title="Test Task",
            description=None,
            user_id=user_id,
            status="pending",
            created_at=created_at,
            updated_at=None,
            completed_at=None,
        )

        data_minimal = dto_minimal.model_dump()
        self.assertIsNone(data_minimal["description"])
        self.assertIsNone(data_minimal["updated_at"])
        self.assertIsNone(data_minimal["completed_at"])


class TestTaskEntityValidation(unittest.TestCase):
    """Test cases for Task entity validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.user_id = uuid4()

    def test_task_entity_valid_data(self):
        """Test Task entity with valid data."""
        # Act
        task = Task(
            title="Test Task", description="Test description", user_id=self.user_id
        )

        # Assert
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.description, "Test description")
        self.assertEqual(task.user_id, self.user_id)
        self.assertEqual(task.status, "pending")  # Default
        self.assertIsNotNone(task.id)
        self.assertIsNotNone(task.created_at)
        self.assertIsNone(task.updated_at)
        self.assertIsNone(task.completed_at)

    def test_task_entity_minimal_valid_data(self):
        """Test Task entity with minimal required data."""
        # Act
        task = Task(title="Test Task", user_id=self.user_id)

        # Assert
        self.assertEqual(task.title, "Test Task")
        self.assertIsNone(task.description)
        self.assertEqual(task.user_id, self.user_id)

    def test_task_entity_title_validation(self):
        """Test Task entity title validation."""
        # Empty title
        with self.assertRaises(ValidationError):
            Task(title="", user_id=self.user_id)

        # Title too long (over 200 characters)
        long_title = "a" * 201
        with self.assertRaises(ValidationError):
            Task(title=long_title, user_id=self.user_id)

        # Valid title at boundary (exactly 200 characters)
        boundary_title = "a" * 200
        task = Task(title=boundary_title, user_id=self.user_id)
        self.assertEqual(task.title, boundary_title)

    def test_task_entity_description_validation(self):
        """Test Task entity description validation."""
        # Description too long (over 1000 characters)
        long_description = "a" * 1001
        with self.assertRaises(ValidationError):
            Task(title="Test Task", description=long_description, user_id=self.user_id)

        # Valid description at boundary (exactly 1000 characters)
        boundary_description = "a" * 1000
        task = Task(
            title="Test Task", description=boundary_description, user_id=self.user_id
        )
        self.assertEqual(task.description, boundary_description)

    def test_task_entity_default_values(self):
        """Test Task entity default values."""
        task = Task(title="Test Task", user_id=self.user_id)

        # Test defaults
        self.assertIsNotNone(task.id)
        self.assertIsNotNone(task.created_at)
        self.assertIsNone(task.updated_at)
        self.assertIsNone(task.completed_at)
        self.assertEqual(task.status, "pending")

        # Test that each task gets unique ID
        task2 = Task(title="Test Task 2", user_id=self.user_id)
        self.assertNotEqual(task.id, task2.id)

        # Test that created_at is recent
        now = datetime.now(timezone.utc)
        self.assertLess((now - task.created_at).total_seconds(), 1)

    def test_task_entity_business_methods(self):
        """Test Task entity business methods."""
        task = Task(title="Test Task", user_id=self.user_id)
        original_created_at = task.created_at

        # Test start()
        self.assertEqual(task.status, "pending")
        task.start()
        self.assertEqual(task.status, "running")
        self.assertIsNotNone(task.updated_at)
        self.assertEqual(task.created_at, original_created_at)  # Should not change
        self.assertIsNone(task.completed_at)  # Should still be None

        # Test complete()
        task.complete()
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.updated_at)
        self.assertIsNotNone(task.completed_at)

        # Test fail() (reset first)
        task2 = Task(title="Test Task 2", user_id=self.user_id)
        task2.fail()
        self.assertEqual(task2.status, "failed")
        self.assertIsNotNone(task2.updated_at)
        self.assertIsNone(task2.completed_at)  # Failed tasks don't get completed_at

    def test_task_entity_update_details_method(self):
        """Test Task entity update_details method."""
        task = Task(title="Original Title", user_id=self.user_id)

        # Update title only
        task.update_details("New Title")
        self.assertEqual(task.title, "New Title")
        self.assertIsNone(task.description)  # Should remain None
        self.assertIsNotNone(task.updated_at)

        # Update title and description
        task.update_details("Newer Title", "New description")
        self.assertEqual(task.title, "Newer Title")
        self.assertEqual(task.description, "New description")

        # Update with explicit None description (should set to None)
        task.update_details("Final Title", None)
        self.assertEqual(task.title, "Final Title")
        self.assertIsNone(task.description)

    def test_task_entity_serialization(self):
        """Test Task entity field serialization."""
        task_id = uuid4()
        user_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)

        task = Task(
            id=task_id,
            title="Test Task",
            description="Test description",
            user_id=user_id,
            status="completed",
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
        )

        # Test serialization
        data = task.model_dump()
        self.assertEqual(data["id"], str(task_id))  # Should be serialized as string
        self.assertEqual(
            data["user_id"], str(user_id)
        )  # Should be serialized as string
        self.assertEqual(data["title"], "Test Task")
        self.assertEqual(data["description"], "Test description")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["created_at"], created_at.isoformat())
        self.assertEqual(data["updated_at"], updated_at.isoformat())
        self.assertEqual(data["completed_at"], completed_at.isoformat())

        # Test with None optional fields
        task_minimal = Task(title="Minimal Task", user_id=user_id)
        data_minimal = task_minimal.model_dump()
        self.assertIsNone(data_minimal["description"])
        self.assertIsNone(data_minimal["updated_at"])
        self.assertIsNone(data_minimal["completed_at"])

    def test_task_entity_status_transitions(self):
        """Test valid status transitions through business methods."""
        task = Task(title="Test Task", user_id=self.user_id)

        # pending -> running
        self.assertEqual(task.status, "pending")
        task.start()
        self.assertEqual(task.status, "running")

        # running -> completed
        task.complete()
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.completed_at)

        # Test pending -> failed
        task2 = Task(title="Test Task 2", user_id=self.user_id)
        task2.fail()
        self.assertEqual(task2.status, "failed")
        self.assertIsNone(task2.completed_at)

        # Test running -> failed
        task3 = Task(title="Test Task 3", user_id=self.user_id)
        task3.start()
        task3.fail()
        self.assertEqual(task3.status, "failed")

    def test_task_entity_immutable_fields(self):
        """Test that certain fields should not be directly modified."""
        task = Task(title="Test Task", user_id=self.user_id)
        original_id = task.id
        original_created_at = task.created_at
        original_user_id = task.user_id

        # These should be immutable after creation
        self.assertEqual(task.id, original_id)
        self.assertEqual(task.created_at, original_created_at)
        self.assertEqual(task.user_id, original_user_id)

    def test_task_entity_update_timestamps(self):
        """Test that business methods properly update timestamps."""
        task = Task(title="Test Task", user_id=self.user_id)

        # Initially no updated_at
        self.assertIsNone(task.updated_at)

        # After start, should have updated_at
        task.start()
        self.assertIsNotNone(task.updated_at)
        first_update = task.updated_at

        # After complete, should update timestamp
        import time

        time.sleep(0.001)  # Ensure different timestamp
        task.complete()
        self.assertIsNotNone(task.updated_at)
        self.assertNotEqual(task.updated_at, first_update)
        self.assertIsNotNone(task.completed_at)

        # Test update_details updates timestamp
        task2 = Task(title="Test Task 2", user_id=self.user_id)
        self.assertIsNone(task2.updated_at)
        task2.update_details("New Title")
        self.assertIsNotNone(task2.updated_at)

    def test_task_entity_completed_at_behavior(self):
        """Test completed_at field behavior."""
        task = Task(title="Test Task", user_id=self.user_id)

        # Initially None
        self.assertIsNone(task.completed_at)

        # After start, still None
        task.start()
        self.assertIsNone(task.completed_at)

        # After complete, should be set
        task.complete()
        self.assertIsNotNone(task.completed_at)

        # After fail, should remain None
        task2 = Task(title="Test Task 2", user_id=self.user_id)
        task2.fail()
        self.assertIsNone(task2.completed_at)


if __name__ == "__main__":
    unittest.main()
