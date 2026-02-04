"""Unit tests for payment validators (pure functions)."""

import pytest

from nanomoni.application.vendor.use_cases.payment_validators import (
    validate_payment_amount,
    check_duplicate_payment,
    validate_vendor_ownership,
)


class TestValidatePaymentAmount:
    """Test validate_payment_amount function."""

    def test_validate_payment_amount_increasing(self) -> None:
        """Payment amount must be strictly increasing."""
        validate_payment_amount(new_amount=200, prev_amount=100, channel_amount=1000)
        # Should not raise

    def test_validate_payment_amount_decreasing_raises(self) -> None:
        """Decreasing amount should raise ValueError."""
        with pytest.raises(ValueError, match="must be increasing"):
            validate_payment_amount(new_amount=50, prev_amount=100, channel_amount=1000)

    def test_validate_payment_amount_equal_allowed(self) -> None:
        """Equal amount should be allowed (duplicate check handles it separately)."""
        # Equal amounts are handled by check_duplicate_payment, not validate_payment_amount
        validate_payment_amount(new_amount=100, prev_amount=100, channel_amount=1000)
        # Should not raise (duplicate check will handle it)

    def test_validate_payment_amount_exceeds_channel_raises(self) -> None:
        """Amount exceeding channel should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds payment channel amount"):
            validate_payment_amount(
                new_amount=1500, prev_amount=100, channel_amount=1000
            )

    def test_validate_payment_amount_at_channel_limit(self) -> None:
        """Amount equal to channel limit should be valid."""
        validate_payment_amount(new_amount=1000, prev_amount=100, channel_amount=1000)
        # Should not raise

    def test_validate_payment_amount_first_payment(self) -> None:
        """First payment (prev_amount=0) should be valid."""
        validate_payment_amount(new_amount=100, prev_amount=0, channel_amount=1000)
        # Should not raise


class TestCheckDuplicatePayment:
    """Test check_duplicate_payment function."""

    def test_check_duplicate_payment_valid_duplicate(self) -> None:
        """Valid duplicate (same amount and signature) should return True."""
        result = check_duplicate_payment(
            new_amount=100,
            new_signature="sig1",
            prev_amount=100,
            prev_signature="sig1",
        )
        assert result is True

    def test_check_duplicate_payment_replay_attack_raises(self) -> None:
        """Duplicate amount with different signature should raise ValueError."""
        with pytest.raises(ValueError, match="mismatched signature"):
            check_duplicate_payment(
                new_amount=100,
                new_signature="sig1",
                prev_amount=100,
                prev_signature="sig2",
            )

    def test_check_duplicate_payment_different_amount(self) -> None:
        """Different amount should return False."""
        result = check_duplicate_payment(
            new_amount=200,
            new_signature="sig1",
            prev_amount=100,
            prev_signature="sig1",
        )
        assert result is False

    def test_check_duplicate_payment_no_previous(self) -> None:
        """No previous payment should return False."""
        result = check_duplicate_payment(
            new_amount=100,
            new_signature="sig1",
            prev_amount=0,
            prev_signature=None,
        )
        assert result is False


class TestValidateVendorOwnership:
    """Test validate_vendor_ownership function."""

    def test_validate_vendor_ownership_matching(self) -> None:
        """Matching vendor keys should not raise."""
        validate_vendor_ownership(
            channel_vendor_key="vendor_key_123", vendor_key="vendor_key_123"
        )
        # Should not raise

    def test_validate_vendor_ownership_mismatch_raises(self) -> None:
        """Mismatched vendor keys should raise ValueError."""
        with pytest.raises(ValueError, match="not for this vendor"):
            validate_vendor_ownership(
                channel_vendor_key="vendor_key_123", vendor_key="vendor_key_456"
            )
