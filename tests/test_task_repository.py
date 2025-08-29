"""Integration tests for Task repository database operations."""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from src.nanomoni.infrastructure.database import DatabaseClient
from src.nanomoni.infrastructure.repositories import SQLiteTaskRepository
from src.nanomoni.domain.entities import Task
from src.nanomoni.env import Settings


class TestSQLiteTaskRepositoryIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration test cases for SQLiteTaskRepository."""

    def setUp(self):
        """Set up test fixtures with temporary database."""
        # Create temporary database file
        self.db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_file.close()

        # Create settings with the temporary database path
        self.settings = Settings(
            secret="test-secret", database_url=f"sqlite:///{self.db_file.name}"
        )

        # Initialize database client and repository
        self.db_client = DatabaseClient(self.settings)
        self.db_client.initialize_database()
        self.repository = SQLiteTaskRepository(self.db_client)

        # Test data
        self.task_id = uuid4()
        self.user_id = uuid4()
        self.test_task = Task(
            id=self.task_id,
            title="Test Task",
            description="Test description",
            user_id=self.user_id,
            status="pending",
        )

        # Create a test user in the database (for foreign key constraint)
        self._create_test_user()

    def tearDown(self):
        """Clean up temporary database file."""
        try:
            os.unlink(self.db_file.name)
        except FileNotFoundError:
            pass

    def _create_test_user(self):
        """Helper method to create a test user in the database."""
        with sqlite3.connect(self.db_file.name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (id, name, email, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(self.user_id),
                    "Test User",
                    "test@example.com",
                    datetime.now(timezone.utc).isoformat(),
                    None,
                    True,
                ),
            )
            conn.commit()

    async def test_create_task_saves_to_database(self):
        """Test that create actually saves task to database."""
        # Act
        created_task = await self.repository.create(self.test_task)

        # Assert
        self.assertEqual(created_task.id, self.test_task.id)
        self.assertEqual(created_task.title, "Test Task")
        self.assertEqual(created_task.description, "Test description")
        self.assertEqual(created_task.user_id, self.user_id)
        self.assertEqual(created_task.status, "pending")

        # Verify in database directly
        with sqlite3.connect(self.db_file.name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (str(self.task_id),))
            row = cursor.fetchone()

            self.assertIsNotNone(row)
            self.assertEqual(row["title"], "Test Task")
            self.assertEqual(row["description"], "Test description")
            self.assertEqual(row["user_id"], str(self.user_id))
            self.assertEqual(row["status"], "pending")
            self.assertIsNotNone(row["created_at"])
            self.assertIsNone(row["updated_at"])
            self.assertIsNone(row["completed_at"])

    async def test_create_task_minimal_data(self):
        """Test creating task with minimal required data."""
        # Arrange
        minimal_task = Task(
            title="Minimal Task", user_id=self.user_id, status="pending"
        )

        # Act
        created_task = await self.repository.create(minimal_task)

        # Assert
        self.assertEqual(created_task.title, "Minimal Task")
        self.assertIsNone(created_task.description)
        self.assertEqual(created_task.user_id, self.user_id)
        self.assertEqual(created_task.status, "pending")

    async def test_get_by_id_retrieves_from_database(self):
        """Test that get_by_id actually retrieves from database."""
        # Arrange - Insert task directly into database
        with sqlite3.connect(self.db_file.name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (id, title, description, user_id, status, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(self.task_id),
                    "Test Task",
                    "Test description",
                    str(self.user_id),
                    "pending",
                    datetime.now(timezone.utc).isoformat(),
                    None,
                    None,
                ),
            )
            conn.commit()

        # Act
        retrieved_task = await self.repository.get_by_id(self.task_id)

        # Assert
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.id, self.task_id)
        self.assertEqual(retrieved_task.title, "Test Task")
        self.assertEqual(retrieved_task.description, "Test description")
        self.assertEqual(retrieved_task.user_id, self.user_id)
        self.assertEqual(retrieved_task.status, "pending")

    async def test_get_by_id_nonexistent_returns_none(self):
        """Test that get_by_id returns None for non-existent task."""
        # Act
        result = await self.repository.get_by_id(uuid4())

        # Assert
        self.assertIsNone(result)

    async def test_get_all_with_pagination(self):
        """Test that get_all retrieves tasks with pagination."""
        # Arrange - Create multiple tasks
        tasks = []
        for i in range(5):
            task = Task(
                title=f"Task {i}",
                description=f"Description {i}",
                user_id=self.user_id,
                status="pending",
            )
            tasks.append(task)
            await self.repository.create(task)

        # Act
        result = await self.repository.get_all(skip=1, limit=2)

        # Assert
        self.assertEqual(len(result), 2)
        # Results should be ordered by created_at DESC
        self.assertIn(result[0].title, [f"Task {i}" for i in range(5)])
        self.assertIn(result[1].title, [f"Task {i}" for i in range(5)])

    async def test_get_all_empty_database(self):
        """Test that get_all returns empty list for empty database."""
        # Act
        result = await self.repository.get_all()

        # Assert
        self.assertEqual(len(result), 0)

    async def test_get_all_ordering(self):
        """Test that get_all returns tasks ordered by created_at DESC."""
        import time

        # Arrange - Create tasks with slight time differences
        first_task = Task(title="First Task", user_id=self.user_id, status="pending")
        await self.repository.create(first_task)

        time.sleep(0.01)

        second_task = Task(title="Second Task", user_id=self.user_id, status="pending")
        await self.repository.create(second_task)

        # Act
        result = await self.repository.get_all()

        # Assert
        self.assertEqual(len(result), 2)
        # Should be newest first (DESC order)
        self.assertEqual(result[0].title, "Second Task")
        self.assertEqual(result[1].title, "First Task")

    async def test_get_by_user_id_retrieves_user_tasks(self):
        """Test that get_by_user_id retrieves tasks for specific user."""
        # Arrange - Create another user and tasks for both users
        other_user_id = uuid4()
        with sqlite3.connect(self.db_file.name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (id, name, email, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(other_user_id),
                    "Other User",
                    "other@example.com",
                    datetime.now(timezone.utc).isoformat(),
                    None,
                    True,
                ),
            )
            conn.commit()

        # Create tasks for original user
        task1 = Task(title="User 1 Task 1", user_id=self.user_id, status="pending")
        task2 = Task(title="User 1 Task 2", user_id=self.user_id, status="completed")
        await self.repository.create(task1)
        await self.repository.create(task2)

        # Create task for other user
        task3 = Task(title="User 2 Task 1", user_id=other_user_id, status="pending")
        await self.repository.create(task3)

        # Act
        user_tasks = await self.repository.get_by_user_id(self.user_id)
        other_user_tasks = await self.repository.get_by_user_id(other_user_id)

        # Assert
        self.assertEqual(len(user_tasks), 2)
        self.assertEqual(len(other_user_tasks), 1)

        user_task_titles = [task.title for task in user_tasks]
        self.assertIn("User 1 Task 1", user_task_titles)
        self.assertIn("User 1 Task 2", user_task_titles)

        self.assertEqual(other_user_tasks[0].title, "User 2 Task 1")

    async def test_get_by_user_id_with_pagination(self):
        """Test get_by_user_id with pagination."""
        # Arrange - Create multiple tasks for the user
        for i in range(5):
            task = Task(title=f"User Task {i}", user_id=self.user_id, status="pending")
            await self.repository.create(task)

        # Act
        result = await self.repository.get_by_user_id(self.user_id, skip=1, limit=2)

        # Assert
        self.assertEqual(len(result), 2)

    async def test_get_by_status_retrieves_status_tasks(self):
        """Test that get_by_status retrieves tasks with specific status."""
        # Arrange - Create tasks with different statuses
        pending_task = Task(
            title="Pending Task", user_id=self.user_id, status="pending"
        )
        running_task = Task(
            title="Running Task", user_id=self.user_id, status="running"
        )
        completed_task = Task(
            title="Completed Task", user_id=self.user_id, status="completed"
        )

        await self.repository.create(pending_task)
        await self.repository.create(running_task)
        await self.repository.create(completed_task)

        # Act
        pending_tasks = await self.repository.get_by_status("pending")
        running_tasks = await self.repository.get_by_status("running")
        completed_tasks = await self.repository.get_by_status("completed")
        failed_tasks = await self.repository.get_by_status("failed")

        # Assert
        self.assertEqual(len(pending_tasks), 1)
        self.assertEqual(len(running_tasks), 1)
        self.assertEqual(len(completed_tasks), 1)
        self.assertEqual(len(failed_tasks), 0)

        self.assertEqual(pending_tasks[0].title, "Pending Task")
        self.assertEqual(running_tasks[0].title, "Running Task")
        self.assertEqual(completed_tasks[0].title, "Completed Task")

    async def test_get_by_status_with_pagination(self):
        """Test get_by_status with pagination."""
        # Arrange - Create multiple pending tasks
        for i in range(5):
            task = Task(
                title=f"Pending Task {i}", user_id=self.user_id, status="pending"
            )
            await self.repository.create(task)

        # Act
        result = await self.repository.get_by_status("pending", skip=1, limit=2)

        # Assert
        self.assertEqual(len(result), 2)
        for task in result:
            self.assertEqual(task.status, "pending")

    async def test_update_task_modifies_database(self):
        """Test that update actually modifies task in database."""
        # Arrange
        created_task = await self.repository.create(self.test_task)
        created_task.title = "Updated Task"
        created_task.description = "Updated description"
        created_task.status = "running"
        created_task.update_details(created_task.title, created_task.description)

        # Act
        updated_task = await self.repository.update(created_task)

        # Assert
        self.assertEqual(updated_task.title, "Updated Task")
        self.assertEqual(updated_task.description, "Updated description")
        self.assertEqual(updated_task.status, "running")
        self.assertIsNotNone(updated_task.updated_at)

        # Verify in database directly
        with sqlite3.connect(self.db_file.name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (str(self.task_id),))
            row = cursor.fetchone()

            self.assertEqual(row["title"], "Updated Task")
            self.assertEqual(row["description"], "Updated description")
            self.assertEqual(row["status"], "running")
            self.assertIsNotNone(row["updated_at"])

    async def test_update_task_with_completion(self):
        """Test updating task with completion."""
        # Arrange
        created_task = await self.repository.create(self.test_task)
        created_task.complete()

        # Act
        updated_task = await self.repository.update(created_task)

        # Assert
        self.assertEqual(updated_task.status, "completed")
        self.assertIsNotNone(updated_task.completed_at)

        # Verify in database
        retrieved_task = await self.repository.get_by_id(self.task_id)
        self.assertEqual(retrieved_task.status, "completed")
        self.assertIsNotNone(retrieved_task.completed_at)

    async def test_delete_task_removes_from_database(self):
        """Test that delete actually removes task from database."""
        # Arrange
        await self.repository.create(self.test_task)

        # Act
        success = await self.repository.delete(self.task_id)

        # Assert
        self.assertTrue(success)

        # Verify task is deleted
        retrieved_task = await self.repository.get_by_id(self.task_id)
        self.assertIsNone(retrieved_task)

    async def test_delete_nonexistent_task_returns_false(self):
        """Test that deleting non-existent task returns False."""
        # Act
        success = await self.repository.delete(uuid4())

        # Assert
        self.assertFalse(success)

    async def test_foreign_key_constraint(self):
        """Test that foreign key constraint is enforced."""
        # Arrange - Task with non-existent user_id
        invalid_task = Task(
            title="Invalid Task",
            user_id=uuid4(),  # Non-existent user
            status="pending",
        )

        # Act & Assert
        with self.assertRaises(sqlite3.IntegrityError) as context:
            await self.repository.create(invalid_task)

        self.assertIn("FOREIGN KEY constraint failed", str(context.exception))

    async def test_row_to_task_conversion(self):
        """Test internal _row_to_task conversion method."""
        # Arrange - Create task with all fields
        complete_task = Task(
            id=self.task_id,
            title="Complete Task",
            description="Complete description",
            user_id=self.user_id,
            status="completed",
            updated_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        await self.repository.create(complete_task)

        # Act
        retrieved_task = await self.repository.get_by_id(self.task_id)

        # Assert - Verify all fields are properly converted
        self.assertIsInstance(retrieved_task.id, type(self.task_id))
        self.assertIsInstance(retrieved_task.user_id, type(self.user_id))
        self.assertIsInstance(retrieved_task.title, str)
        self.assertIsInstance(retrieved_task.description, str)
        self.assertIsInstance(retrieved_task.status, str)
        self.assertIsInstance(retrieved_task.created_at, datetime)
        self.assertIsInstance(retrieved_task.updated_at, datetime)
        self.assertIsInstance(retrieved_task.completed_at, datetime)

    async def test_row_to_task_with_null_fields(self):
        """Test _row_to_task handles NULL fields correctly."""
        # Arrange
        minimal_task = Task(
            title="Minimal Task", user_id=self.user_id, status="pending"
        )
        await self.repository.create(minimal_task)

        # Act
        retrieved_task = await self.repository.get_by_id(minimal_task.id)

        # Assert
        self.assertIsNone(retrieved_task.description)
        self.assertIsNone(retrieved_task.updated_at)
        self.assertIsNone(retrieved_task.completed_at)

    async def test_concurrent_task_operations(self):
        """Test concurrent task operations."""
        import asyncio

        # Create multiple tasks concurrently
        async def create_task(index):
            task = Task(
                title=f"Concurrent Task {index}",
                description=f"Description {index}",
                user_id=self.user_id,
                status="pending",
            )
            return await self.repository.create(task)

        # Act
        tasks = [create_task(i) for i in range(5)]
        created_tasks = await asyncio.gather(*tasks)

        # Assert
        self.assertEqual(len(created_tasks), 5)

        # Verify all tasks are in database
        all_tasks = await self.repository.get_all()
        self.assertEqual(len(all_tasks), 5)

    async def test_task_status_filtering(self):
        """Test comprehensive status filtering."""
        # Arrange - Create tasks with all possible statuses
        statuses = ["pending", "running", "completed", "failed"]
        for status in statuses:
            task = Task(title=f"Task {status}", user_id=self.user_id, status=status)
            await self.repository.create(task)

        # Act & Assert
        for status in statuses:
            tasks = await self.repository.get_by_status(status)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].status, status)
            self.assertEqual(tasks[0].title, f"Task {status}")

    async def test_large_data_handling(self):
        """Test repository handles large data correctly."""
        # Test with maximum length values
        long_title = "a" * 200  # Max length
        long_description = "b" * 1000  # Max length

        large_task = Task(
            title=long_title,
            description=long_description,
            user_id=self.user_id,
            status="pending",
        )

        # Act
        created_task = await self.repository.create(large_task)
        retrieved_task = await self.repository.get_by_id(created_task.id)

        # Assert
        self.assertEqual(retrieved_task.title, long_title)
        self.assertEqual(retrieved_task.description, long_description)

    async def test_special_characters_in_task_data(self):
        """Test repository handles special characters correctly."""
        special_task = Task(
            title="Task with 'quotes' & special chars: @#$%",
            description="Description with\nnewlines and\ttabs",
            user_id=self.user_id,
            status="pending",
        )

        # Act
        created_task = await self.repository.create(special_task)
        retrieved_task = await self.repository.get_by_id(created_task.id)

        # Assert
        self.assertEqual(
            retrieved_task.title, "Task with 'quotes' & special chars: @#$%"
        )
        self.assertEqual(
            retrieved_task.description, "Description with\nnewlines and\ttabs"
        )

    async def test_task_user_relationship(self):
        """Test that task-user relationship is maintained."""
        # Arrange - Create task
        await self.repository.create(self.test_task)

        # Act - Get task and verify user_id
        retrieved_task = await self.repository.get_by_id(self.task_id)

        # Assert
        self.assertEqual(retrieved_task.user_id, self.user_id)

        # Verify user still exists in database
        with sqlite3.connect(self.db_file.name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (str(self.user_id),))
            user_row = cursor.fetchone()
            self.assertIsNotNone(user_row)

    async def test_cascade_delete_behavior(self):
        """Test cascade delete behavior when user is deleted."""
        # Arrange - Create task
        await self.repository.create(self.test_task)

        # Delete the user (should cascade to tasks)
        with sqlite3.connect(self.db_file.name) as conn:
            conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (str(self.user_id),))
            conn.commit()

        # Act - Try to retrieve task
        retrieved_task = await self.repository.get_by_id(self.task_id)

        # Assert - Task should be deleted due to cascade
        self.assertIsNone(retrieved_task)


class TestTaskRepositoryErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test task repository error handling scenarios."""

    async def test_database_connection_error_handling(self):
        """Test that database connection errors are properly handled."""
        # Create temporary database file
        db_file = tempfile.NamedTemporaryFile(delete=False)
        db_file.close()

        try:
            test_settings = Settings(
                secret="test-secret", database_url=f"sqlite:///{db_file.name}"
            )
            db_client = DatabaseClient(test_settings)
            db_client.initialize_database()
            repository = SQLiteTaskRepository(db_client)

            # Delete the database file to simulate connection issues
            os.unlink(db_file.name)

            task = Task(title="Test", user_id=uuid4(), status="pending")

            # Act & Assert - Should raise an error when trying to use deleted database
            with self.assertRaises((sqlite3.OperationalError, FileNotFoundError)):
                await repository.create(task)
        finally:
            # Clean up if file still exists
            try:
                os.unlink(db_file.name)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
