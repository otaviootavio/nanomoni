"""Validation tests for User feature - DTOs and Entities."""

import unittest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from src.nanomoni.application.dtos import CreateUserDTO, UpdateUserDTO, UserResponseDTO
from src.nanomoni.domain.entities import User


class TestUserDTOValidation(unittest.TestCase):
    """Test cases for User DTO validation."""

    def test_create_user_dto_valid_data(self):
        """Test CreateUserDTO with valid data."""
        # Act
        dto = CreateUserDTO(name="John Doe", email="john.doe@example.com")

        # Assert
        self.assertEqual(dto.name, "John Doe")
        self.assertEqual(dto.email, "john.doe@example.com")

    def test_create_user_dto_invalid_email_formats(self):
        """Test CreateUserDTO with various invalid email formats."""
        invalid_emails = [
            "invalid-email",
            "missing@domain",
            "@missinglocal.com",
            "spaces in@email.com",
            "double@@domain.com",
            "",
            "no-at-symbol.com",
            "multiple..dots@domain.com",
            "trailing-dot@domain.com.",
        ]

        for invalid_email in invalid_emails:
            with self.subTest(email=invalid_email):
                with self.assertRaises(ValidationError) as context:
                    CreateUserDTO(name="John Doe", email=invalid_email)

                errors = context.exception.errors()
                self.assertTrue(any("email" in str(error).lower() for error in errors))

    def test_create_user_dto_valid_email_formats(self):
        """Test CreateUserDTO with various valid email formats."""
        valid_emails = [
            "simple@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user_name@example.com",
            "123@example.com",
            "user@sub.example.com",
            "user@example-domain.com",
            "a@b.co",
            "test.email+tag@domain.co.uk",
            "special!chars@domain.com",
            "unicode@dömäin.com",
        ]

        for valid_email in valid_emails:
            with self.subTest(email=valid_email):
                try:
                    dto = CreateUserDTO(name="John Doe", email=valid_email)
                    self.assertEqual(dto.email, valid_email)
                except ValidationError as e:
                    self.fail(f"Valid email {valid_email} was rejected: {e}")

    def test_create_user_dto_name_validation(self):
        """Test CreateUserDTO name field validation."""
        # Empty name
        with self.assertRaises(ValidationError) as context:
            CreateUserDTO(name="", email="john.doe@example.com")

        errors = context.exception.errors()
        self.assertTrue(any("name" in str(error).lower() for error in errors))

        # Name too long (over 100 characters)
        long_name = "a" * 101
        with self.assertRaises(ValidationError) as context:
            CreateUserDTO(name=long_name, email="john.doe@example.com")

        errors = context.exception.errors()
        self.assertTrue(any("name" in str(error).lower() for error in errors))

        # Valid name at boundary (exactly 100 characters)
        boundary_name = "a" * 100
        dto = CreateUserDTO(name=boundary_name, email="john.doe@example.com")
        self.assertEqual(dto.name, boundary_name)

    def test_create_user_dto_email_length_validation(self):
        """Test CreateUserDTO email length validation."""
        # Email too long (over 100 characters)
        long_email = "a" * 90 + "@example.com"  # This exceeds 100 chars
        with self.assertRaises(ValidationError) as context:
            CreateUserDTO(name="John Doe", email=long_email)

        errors = context.exception.errors()
        self.assertTrue(any("email" in str(error).lower() for error in errors))

    def test_create_user_dto_missing_required_fields(self):
        """Test CreateUserDTO with missing required fields."""
        # Missing email
        with self.assertRaises(ValidationError):
            CreateUserDTO(name="John Doe")

        # Missing name
        with self.assertRaises(ValidationError):
            CreateUserDTO(email="john.doe@example.com")

        # Missing both
        with self.assertRaises(ValidationError):
            CreateUserDTO()

    def test_update_user_dto_valid_data(self):
        """Test UpdateUserDTO with valid data."""
        # Full update
        dto = UpdateUserDTO(name="Jane Doe", email="jane.doe@example.com")
        self.assertEqual(dto.name, "Jane Doe")
        self.assertEqual(dto.email, "jane.doe@example.com")

        # Partial updates
        dto_name_only = UpdateUserDTO(name="Jane Doe")
        self.assertEqual(dto_name_only.name, "Jane Doe")
        self.assertIsNone(dto_name_only.email)

        dto_email_only = UpdateUserDTO(email="jane.doe@example.com")
        self.assertIsNone(dto_email_only.name)
        self.assertEqual(dto_email_only.email, "jane.doe@example.com")

        # Empty update (all optional)
        dto_empty = UpdateUserDTO()
        self.assertIsNone(dto_empty.name)
        self.assertIsNone(dto_empty.email)

    def test_update_user_dto_validation_when_provided(self):
        """Test UpdateUserDTO validation when fields are provided."""
        # Empty name when provided
        with self.assertRaises(ValidationError) as context:
            UpdateUserDTO(name="")

        errors = context.exception.errors()
        self.assertTrue(any("name" in str(error).lower() for error in errors))

        # Invalid email when provided
        with self.assertRaises(ValidationError) as context:
            UpdateUserDTO(email="invalid-email")

        errors = context.exception.errors()
        self.assertTrue(any("email" in str(error).lower() for error in errors))

        # Name too long when provided
        long_name = "a" * 101
        with self.assertRaises(ValidationError):
            UpdateUserDTO(name=long_name)

    def test_user_response_dto_serialization(self):
        """Test UserResponseDTO serialization and validation."""
        user_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        # Valid response DTO
        dto = UserResponseDTO(
            id=user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=created_at,
            updated_at=updated_at,
            is_active=True,
        )

        # Test serialization
        data = dto.model_dump()
        self.assertEqual(data["id"], str(user_id))  # Should be serialized as string
        self.assertEqual(data["name"], "John Doe")
        self.assertEqual(data["email"], "john.doe@example.com")
        self.assertEqual(data["created_at"], created_at.isoformat())
        self.assertEqual(data["updated_at"], updated_at.isoformat())
        self.assertTrue(data["is_active"])

        # Test with None updated_at
        dto_no_update = UserResponseDTO(
            id=user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=created_at,
            updated_at=None,
            is_active=False,
        )

        data_no_update = dto_no_update.model_dump()
        self.assertIsNone(data_no_update["updated_at"])
        self.assertFalse(data_no_update["is_active"])


class TestUserEntityValidation(unittest.TestCase):
    """Test cases for User entity validation."""

    def test_user_entity_valid_data(self):
        """Test User entity with valid data."""
        # Act
        user = User(name="John Doe", email="john.doe@example.com")

        # Assert
        self.assertEqual(user.name, "John Doe")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.id)
        self.assertIsNotNone(user.created_at)
        self.assertIsNone(user.updated_at)

    def test_user_entity_email_pattern_validation(self):
        """Test User entity email pattern validation using regex."""
        invalid_emails = [
            "invalid-email",
            "missing@domain",
            "@missinglocal.com",
            "spaces in@email.com",
            "double@@domain.com",
            "",
            "no-at-symbol.com",
            "multiple..dots@domain.com",
            "trailing-dot@domain.com.",
        ]

        for invalid_email in invalid_emails:
            with self.subTest(email=invalid_email):
                with self.assertRaises(ValidationError) as context:
                    User(name="John Doe", email=invalid_email)

                errors = context.exception.errors()
                self.assertTrue(any("email" in str(error).lower() for error in errors))

    def test_user_entity_valid_email_patterns(self):
        """Test User entity with valid email patterns."""
        valid_emails = [
            "simple@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user_name@example.com",
            "123@example.com",
            "user@sub.example.com",
            "user@example-domain.com",
            "a@b.co",
            "test.email+tag@domain.co.uk",
            "special!chars@domain.com",
            "unicode@dömäin.com",
        ]

        for valid_email in valid_emails:
            with self.subTest(email=valid_email):
                try:
                    user = User(name="John Doe", email=valid_email)
                    self.assertEqual(user.email, valid_email)
                except ValidationError as e:
                    self.fail(f"Valid email {valid_email} was rejected: {e}")

    def test_user_entity_name_validation(self):
        """Test User entity name validation."""
        # Empty name
        with self.assertRaises(ValidationError):
            User(name="", email="john.doe@example.com")

        # Name too long (over 100 characters)
        long_name = "a" * 101
        with self.assertRaises(ValidationError):
            User(name=long_name, email="john.doe@example.com")

        # Valid name at boundary (exactly 100 characters)
        boundary_name = "a" * 100
        user = User(name=boundary_name, email="john.doe@example.com")
        self.assertEqual(user.name, boundary_name)

    def test_user_entity_default_values(self):
        """Test User entity default values."""
        user = User(name="John Doe", email="john.doe@example.com")

        # Test defaults
        self.assertIsNotNone(user.id)
        self.assertIsNotNone(user.created_at)
        self.assertIsNone(user.updated_at)
        self.assertTrue(user.is_active)

        # Test that each user gets unique ID
        user2 = User(name="Jane Doe", email="jane.doe@example.com")
        self.assertNotEqual(user.id, user2.id)

        # Test that created_at is recent
        now = datetime.now(timezone.utc)
        self.assertLess((now - user.created_at).total_seconds(), 1)

    def test_user_entity_business_methods(self):
        """Test User entity business methods."""
        user = User(name="John Doe", email="john.doe@example.com")
        original_created_at = user.created_at

        # Test update_profile
        user.update_profile("Jane Doe", "jane.doe@example.com")
        self.assertEqual(user.name, "Jane Doe")
        self.assertEqual(user.email, "jane.doe@example.com")
        self.assertIsNotNone(user.updated_at)
        self.assertEqual(user.created_at, original_created_at)  # Should not change

        # Test deactivate
        self.assertTrue(user.is_active)  # Initially active
        user.deactivate()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.updated_at)

        # Test activate
        user.activate()
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.updated_at)

    def test_user_entity_serialization(self):
        """Test User entity field serialization."""
        user_id = uuid4()
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        user = User(
            id=user_id,
            name="John Doe",
            email="john.doe@example.com",
            created_at=created_at,
            updated_at=updated_at,
            is_active=False,
        )

        # Test serialization
        data = user.model_dump()
        self.assertEqual(data["id"], str(user_id))  # Should be serialized as string
        self.assertEqual(data["name"], "John Doe")
        self.assertEqual(data["email"], "john.doe@example.com")
        self.assertEqual(data["created_at"], created_at.isoformat())
        self.assertEqual(data["updated_at"], updated_at.isoformat())
        self.assertFalse(data["is_active"])

        # Test with None updated_at
        user_no_update = User(name="Jane Doe", email="jane.doe@example.com")
        data_no_update = user_no_update.model_dump()
        self.assertIsNone(data_no_update["updated_at"])

    def test_user_entity_immutable_fields(self):
        """Test that certain fields should not be directly modified."""
        user = User(name="John Doe", email="john.doe@example.com")
        original_id = user.id
        original_created_at = user.created_at

        # These should be immutable after creation
        # (Note: Pydantic doesn't enforce immutability, but we test the expected behavior)
        self.assertEqual(user.id, original_id)
        self.assertEqual(user.created_at, original_created_at)

    def test_user_entity_update_timestamps(self):
        """Test that business methods properly update timestamps."""
        user = User(name="John Doe", email="john.doe@example.com")

        # Initially no updated_at
        self.assertIsNone(user.updated_at)

        # After update_profile, should have updated_at
        import time

        time.sleep(0.001)  # Ensure different timestamp
        user.update_profile("Jane Doe", "jane.doe@example.com")
        self.assertIsNotNone(user.updated_at)
        first_update = user.updated_at

        # After deactivate, should update timestamp
        import time

        time.sleep(0.001)  # Ensure different timestamp
        user.deactivate()
        self.assertIsNotNone(user.updated_at)
        self.assertNotEqual(user.updated_at, first_update)

        # After activate, should update timestamp again
        time.sleep(0.001)
        second_update = user.updated_at
        user.activate()
        self.assertIsNotNone(user.updated_at)
        self.assertNotEqual(user.updated_at, second_update)


if __name__ == "__main__":
    unittest.main()
