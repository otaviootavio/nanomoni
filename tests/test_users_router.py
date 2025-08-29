"""Unit tests for user API routes."""

import unittest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.nanomoni.api.routers.users import router
from src.nanomoni.api.dependencies import get_user_service
from src.nanomoni.application.dtos import UserResponseDTO


class TestUsersRouter(unittest.TestCase):
    """Test cases for users router."""

    def setUp(self):
        """Set up test fixtures."""
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")

        # Test data
        self.user_id = uuid4()
        self.user_response = UserResponseDTO(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            is_active=True,
        )

        # Create mock service
        self.mock_service = AsyncMock()

        # Override dependency
        self.app.dependency_overrides[get_user_service] = lambda: self.mock_service

        self.client = TestClient(self.app)

    def tearDown(self):
        """Clean up after tests."""
        self.app.dependency_overrides.clear()

    def test_create_user_success(self):
        """Test successful user creation."""
        # Arrange
        self.mock_service.create_user.return_value = self.user_response

        user_data = {"name": "John Doe", "email": "john.doe@example.com"}

        # Act
        response = self.client.post("/api/v1/users/", json=user_data)

        # Assert
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "John Doe")
        self.assertEqual(response.json()["email"], "john.doe@example.com")
        self.mock_service.create_user.assert_called_once()

    def test_get_all_users_success(self):
        """Test successful retrieval of all users."""
        # Arrange
        self.mock_service.get_all_users.return_value = [self.user_response]

        # Act
        response = self.client.get("/api/v1/users/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["name"], "John Doe")
        self.mock_service.get_all_users.assert_called_once_with(skip=0, limit=100)

    def test_get_user_by_id_success(self):
        """Test successful retrieval of user by ID."""
        # Arrange
        self.mock_service.get_user_by_id.return_value = self.user_response

        # Act
        response = self.client.get(f"/api/v1/users/{self.user_id}")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "John Doe")
        self.mock_service.get_user_by_id.assert_called_once_with(self.user_id)

    def test_get_user_by_email_success(self):
        """Test successful retrieval of user by email."""
        # Arrange
        self.mock_service.get_user_by_email.return_value = self.user_response

        # Act
        response = self.client.get("/api/v1/users/email/john.doe@example.com")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "john.doe@example.com")
        self.mock_service.get_user_by_email.assert_called_once_with(
            "john.doe@example.com"
        )

    def test_update_user_success(self):
        """Test successful user update."""
        # Arrange
        updated_user = UserResponseDTO(
            id=self.user_id,
            name="Jane Doe",
            email="jane.doe@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True,
        )

        self.mock_service.update_user.return_value = updated_user

        update_data = {"name": "Jane Doe", "email": "jane.doe@example.com"}

        # Act
        response = self.client.put(f"/api/v1/users/{self.user_id}", json=update_data)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Jane Doe")
        self.mock_service.update_user.assert_called_once()

    def test_delete_user_success(self):
        """Test successful user deletion."""
        # Arrange
        self.mock_service.delete_user.return_value = True

        # Act
        response = self.client.delete(f"/api/v1/users/{self.user_id}")

        # Assert
        self.assertEqual(response.status_code, 204)
        self.mock_service.delete_user.assert_called_once_with(self.user_id)

    def test_deactivate_user_success(self):
        """Test successful user deactivation."""
        # Arrange
        deactivated_user = UserResponseDTO(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=False,
        )

        self.mock_service.deactivate_user.return_value = deactivated_user

        # Act
        response = self.client.patch(f"/api/v1/users/{self.user_id}/deactivate")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_active"], False)
        self.mock_service.deactivate_user.assert_called_once_with(self.user_id)

    def test_activate_user_success(self):
        """Test successful user activation."""
        # Arrange
        activated_user = UserResponseDTO(
            id=self.user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True,
        )

        self.mock_service.activate_user.return_value = activated_user

        # Act
        response = self.client.patch(f"/api/v1/users/{self.user_id}/activate")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_active"], True)
        self.mock_service.activate_user.assert_called_once_with(self.user_id)


if __name__ == "__main__":
    unittest.main()
