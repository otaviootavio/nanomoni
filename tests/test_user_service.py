"""Business logic tests for User service."""

import unittest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.nanomoni.application.use_cases import UserService
from src.nanomoni.application.dtos import CreateUserDTO, UpdateUserDTO, UserResponseDTO
from src.nanomoni.domain.entities import User


class TestUserService(unittest.IsolatedAsyncioTestCase):
    """Test cases for UserService business logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_repository = AsyncMock()
        self.user_service = UserService(self.mock_repository)

        # Test data
        self.user_id = uuid4()
        self.user_entity = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )

    async def test_create_user_success(self):
        """Test successful user creation."""
        # Arrange
        self.mock_repository.exists_by_email.return_value = False
        self.mock_repository.create.return_value = self.user_entity

        dto = CreateUserDTO(name="John Doe", email="john.doe@example.com")

        # Act
        result = await self.user_service.create_user(dto)

        # Assert
        self.assertIsInstance(result, UserResponseDTO)
        self.assertEqual(result.name, "John Doe")
        self.assertEqual(result.email, "john.doe@example.com")
        self.assertEqual(result.id, self.user_id)
        self.assertTrue(result.is_active)

        # Verify repository calls
        self.mock_repository.exists_by_email.assert_called_once_with(
            "john.doe@example.com"
        )
        self.mock_repository.create.assert_called_once()

        # Verify the User entity passed to create has correct data
        call_args = self.mock_repository.create.call_args[0][0]
        self.assertEqual(call_args.name, "John Doe")
        self.assertEqual(call_args.email, "john.doe@example.com")

    async def test_create_user_duplicate_email_raises_error(self):
        """Test that creating user with duplicate email raises ValueError."""
        # Arrange
        self.mock_repository.exists_by_email.return_value = True

        dto = CreateUserDTO(name="John Doe", email="john.doe@example.com")

        # Act & Assert
        with self.assertRaises(ValueError) as context:
            await self.user_service.create_user(dto)

        self.assertEqual(str(context.exception), "User with this email already exists")
        self.mock_repository.exists_by_email.assert_called_once_with(
            "john.doe@example.com"
        )
        self.mock_repository.create.assert_not_called()

    async def test_create_user_email_case_sensitivity(self):
        """Test email uniqueness check is case-insensitive."""
        # Arrange
        self.mock_repository.exists_by_email.return_value = False
        self.mock_repository.create.return_value = self.user_entity

        dto = CreateUserDTO(name="John Doe", email="JOHN.DOE@EXAMPLE.COM")

        # Act
        await self.user_service.create_user(dto)

        # Assert
        self.mock_repository.exists_by_email.assert_called_once_with(
            "john.doe@example.com"
        )

    async def test_get_user_by_id_success(self):
        """Test successful user retrieval by ID."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity

        # Act
        result = await self.user_service.get_user_by_id(self.user_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserResponseDTO)
        self.assertEqual(result.id, self.user_id)
        self.assertEqual(result.name, "John Doe")
        self.assertEqual(result.email, "john.doe@example.com")
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)

    async def test_get_user_by_id_not_found(self):
        """Test user retrieval when user doesn't exist."""
        # Arrange
        self.mock_repository.get_by_id.return_value = None

        # Act
        result = await self.user_service.get_user_by_id(self.user_id)

        # Assert
        self.assertIsNone(result)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)

    async def test_get_user_by_email_success(self):
        """Test successful user retrieval by email."""
        # Arrange
        self.mock_repository.get_by_email.return_value = self.user_entity

        # Act
        result = await self.user_service.get_user_by_email("john.doe@example.com")

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserResponseDTO)
        self.assertEqual(result.email, "john.doe@example.com")
        self.assertEqual(result.name, "John Doe")
        self.mock_repository.get_by_email.assert_called_once_with(
            "john.doe@example.com"
        )

    async def test_get_user_by_email_not_found(self):
        """Test user retrieval by email when user doesn't exist."""
        # Arrange
        self.mock_repository.get_by_email.return_value = None

        # Act
        result = await self.user_service.get_user_by_email("nonexistent@example.com")

        # Assert
        self.assertIsNone(result)
        self.mock_repository.get_by_email.assert_called_once_with(
            "nonexistent@example.com"
        )

    async def test_get_all_users_success(self):
        """Test retrieving all users with default pagination."""
        # Arrange
        users = [self.user_entity]
        self.mock_repository.get_all.return_value = users

        # Act
        result = await self.user_service.get_all_users()

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], UserResponseDTO)
        self.assertEqual(result[0].name, "John Doe")
        self.mock_repository.get_all.assert_called_once_with(skip=0, limit=100)

    async def test_get_all_users_with_pagination(self):
        """Test retrieving all users with custom pagination."""
        # Arrange
        users = [self.user_entity]
        self.mock_repository.get_all.return_value = users

        # Act
        result = await self.user_service.get_all_users(skip=10, limit=5)

        # Assert
        self.assertEqual(len(result), 1)
        self.mock_repository.get_all.assert_called_once_with(skip=10, limit=5)

    async def test_get_all_users_empty_result(self):
        """Test retrieving all users when no users exist."""
        # Arrange
        self.mock_repository.get_all.return_value = []

        # Act
        result = await self.user_service.get_all_users()

        # Assert
        self.assertEqual(len(result), 0)
        self.mock_repository.get_all.assert_called_once_with(skip=0, limit=100)

    async def test_update_user_success(self):
        """Test successful user update."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.exists_by_email.return_value = False

        updated_user = User(
            id=self.user_id,
            name="Jane Doe",
            email="jane.doe@example.com",
            created_at=self.user_entity.created_at,
            updated_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.mock_repository.update.return_value = updated_user

        dto = UpdateUserDTO(name="Jane Doe", email="jane.doe@example.com")

        # Act
        result = await self.user_service.update_user(self.user_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserResponseDTO)
        self.assertEqual(result.name, "Jane Doe")
        self.assertEqual(result.email, "jane.doe@example.com")
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.exists_by_email.assert_called_once_with(
            "jane.doe@example.com"
        )
        self.mock_repository.update.assert_called_once()

    async def test_update_user_not_found(self):
        """Test updating non-existent user returns None."""
        # Arrange
        self.mock_repository.get_by_id.return_value = None

        dto = UpdateUserDTO(name="Jane Doe")

        # Act
        result = await self.user_service.update_user(self.user_id, dto)

        # Assert
        self.assertIsNone(result)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.exists_by_email.assert_not_called()
        self.mock_repository.update.assert_not_called()

    async def test_update_user_duplicate_email_raises_error(self):
        """Test updating user with duplicate email raises ValueError."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.exists_by_email.return_value = True

        dto = UpdateUserDTO(email="existing@example.com")

        # Act & Assert
        with self.assertRaises(ValueError) as context:
            await self.user_service.update_user(self.user_id, dto)

        self.assertEqual(str(context.exception), "User with this email already exists")
        self.mock_repository.exists_by_email.assert_called_once_with(
            "existing@example.com"
        )
        self.mock_repository.update.assert_not_called()

    async def test_update_user_same_email_no_duplicate_check(self):
        """Test updating user with same email doesn't check for duplicates."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.update.return_value = self.user_entity

        dto = UpdateUserDTO(
            name="Updated Name", email="john.doe@example.com"
        )  # Same email

        # Act
        result = await self.user_service.update_user(self.user_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.mock_repository.exists_by_email.assert_not_called()  # Should not check duplicates
        self.mock_repository.update.assert_called_once()

    async def test_update_user_partial_update_name_only(self):
        """Test partial user update - name only."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.update.return_value = self.user_entity

        dto = UpdateUserDTO(name="Updated Name")

        # Act
        result = await self.user_service.update_user(self.user_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.mock_repository.exists_by_email.assert_not_called()  # No email change
        self.mock_repository.update.assert_called_once()

        # Verify the user entity was updated correctly
        updated_user_arg = self.mock_repository.update.call_args[0][0]
        self.assertEqual(updated_user_arg.name, "Updated Name")
        self.assertEqual(updated_user_arg.email, "john.doe@example.com")  # Unchanged

    async def test_update_user_partial_update_email_only(self):
        """Test partial user update - email only."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.exists_by_email.return_value = False
        self.mock_repository.update.return_value = self.user_entity

        dto = UpdateUserDTO(email="newemail@example.com")

        # Act
        result = await self.user_service.update_user(self.user_id, dto)

        # Assert
        self.assertIsNotNone(result)
        self.mock_repository.exists_by_email.assert_called_once_with(
            "newemail@example.com"
        )
        self.mock_repository.update.assert_called_once()

    async def test_update_user_calls_update_profile_method(self):
        """Test that update_user calls the entity's update_profile method."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity
        self.mock_repository.exists_by_email.return_value = False
        self.mock_repository.update.return_value = self.user_entity

        dto = UpdateUserDTO(name="New Name", email="new@example.com")

        # Act
        await self.user_service.update_user(self.user_id, dto)

        # Assert
        # Verify update_profile was called by checking updated_at is set
        updated_user_arg = self.mock_repository.update.call_args[0][0]
        self.assertIsNotNone(updated_user_arg.updated_at)

    async def test_delete_user_success(self):
        """Test successful user deletion."""
        # Arrange
        self.mock_repository.delete.return_value = True

        # Act
        result = await self.user_service.delete_user(self.user_id)

        # Assert
        self.assertTrue(result)
        self.mock_repository.delete.assert_called_once_with(self.user_id)

    async def test_delete_user_not_found(self):
        """Test deleting non-existent user returns False."""
        # Arrange
        self.mock_repository.delete.return_value = False

        # Act
        result = await self.user_service.delete_user(self.user_id)

        # Assert
        self.assertFalse(result)
        self.mock_repository.delete.assert_called_once_with(self.user_id)

    async def test_deactivate_user_success(self):
        """Test successful user deactivation."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity

        deactivated_user = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=self.user_entity.created_at,
            updated_at=datetime.now(timezone.utc),
            is_active=False,
        )
        self.mock_repository.update.return_value = deactivated_user

        # Act
        result = await self.user_service.deactivate_user(self.user_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserResponseDTO)
        self.assertFalse(result.is_active)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.update.assert_called_once()

        # Verify the user entity was deactivated
        updated_user_arg = self.mock_repository.update.call_args[0][0]
        self.assertFalse(updated_user_arg.is_active)
        self.assertIsNotNone(updated_user_arg.updated_at)

    async def test_deactivate_user_not_found(self):
        """Test deactivating non-existent user returns None."""
        # Arrange
        self.mock_repository.get_by_id.return_value = None

        # Act
        result = await self.user_service.deactivate_user(self.user_id)

        # Assert
        self.assertIsNone(result)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.update.assert_not_called()

    async def test_activate_user_success(self):
        """Test successful user activation."""
        # Arrange
        inactive_user = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            is_active=False,
        )
        self.mock_repository.get_by_id.return_value = inactive_user

        activated_user = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=inactive_user.created_at,
            updated_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.mock_repository.update.return_value = activated_user

        # Act
        result = await self.user_service.activate_user(self.user_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserResponseDTO)
        self.assertTrue(result.is_active)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.update.assert_called_once()

        # Verify the user entity was activated
        updated_user_arg = self.mock_repository.update.call_args[0][0]
        self.assertTrue(updated_user_arg.is_active)
        self.assertIsNotNone(updated_user_arg.updated_at)

    async def test_activate_user_not_found(self):
        """Test activating non-existent user returns None."""
        # Arrange
        self.mock_repository.get_by_id.return_value = None

        # Act
        result = await self.user_service.activate_user(self.user_id)

        # Assert
        self.assertIsNone(result)
        self.mock_repository.get_by_id.assert_called_once_with(self.user_id)
        self.mock_repository.update.assert_not_called()

    async def test_activate_already_active_user(self):
        """Test activating an already active user."""
        # Arrange
        self.mock_repository.get_by_id.return_value = self.user_entity  # Already active
        self.mock_repository.update.return_value = self.user_entity

        # Act
        result = await self.user_service.activate_user(self.user_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertTrue(result.is_active)
        # Should still call update (business rule: always update timestamp)
        self.mock_repository.update.assert_called_once()

    async def test_deactivate_already_inactive_user(self):
        """Test deactivating an already inactive user."""
        # Arrange
        inactive_user = User(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            is_active=False,
        )
        self.mock_repository.get_by_id.return_value = inactive_user
        self.mock_repository.update.return_value = inactive_user

        # Act
        result = await self.user_service.deactivate_user(self.user_id)

        # Assert
        self.assertIsNotNone(result)
        self.assertFalse(result.is_active)
        # Should still call update (business rule: always update timestamp)
        self.mock_repository.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
