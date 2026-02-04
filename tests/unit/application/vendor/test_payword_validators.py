"""Unit tests for PayWord validators (pure functions)."""

import pytest

from nanomoni.application.vendor.use_cases.payword_validators import (
    validate_payword_k,
    validate_payword_amount,
    check_duplicate_payword_payment,
)


class TestValidatePaywordK:
    """Test validate_payword_k function."""

    def test_validate_payword_k_increasing(self) -> None:
        """PayWord k must be strictly increasing."""
        validate_payword_k(k=5, prev_k=3, max_k=10)
        # Should not raise

    def test_validate_payword_k_decreasing_raises(self) -> None:
        """Decreasing k should raise ValueError."""
        with pytest.raises(ValueError, match="must be increasing"):
            validate_payword_k(k=2, prev_k=3, max_k=10)

    def test_validate_payword_k_equal_raises(self) -> None:
        """Equal k should raise ValueError (must be strictly increasing)."""
        with pytest.raises(ValueError, match="must be increasing"):
            validate_payword_k(k=3, prev_k=3, max_k=10)

    def test_validate_payword_k_exceeds_max_raises(self) -> None:
        """k exceeding max_k should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds channel max_k"):
            validate_payword_k(k=11, prev_k=3, max_k=10)

    def test_validate_payword_k_at_max_limit(self) -> None:
        """k equal to max_k should be valid."""
        validate_payword_k(k=10, prev_k=3, max_k=10)
        # Should not raise

    def test_validate_payword_k_first_payment(self) -> None:
        """First payment (prev_k=0) should be valid."""
        validate_payword_k(k=1, prev_k=0, max_k=10)
        # Should not raise


class TestValidatePaywordAmount:
    """Test validate_payword_amount function."""

    def test_validate_payword_amount_within_limit(self) -> None:
        """Amount within channel limit should be valid."""
        validate_payword_amount(cumulative_owed=500, channel_amount=1000)
        # Should not raise

    def test_validate_payword_amount_exceeds_channel_raises(self) -> None:
        """Amount exceeding channel should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds payment channel amount"):
            validate_payword_amount(cumulative_owed=1500, channel_amount=1000)

    def test_validate_payword_amount_at_channel_limit(self) -> None:
        """Amount equal to channel limit should be valid."""
        validate_payword_amount(cumulative_owed=1000, channel_amount=1000)
        # Should not raise


class TestCheckDuplicatePaywordPayment:
    """Test check_duplicate_payword_payment function."""

    def test_check_duplicate_payword_payment_valid_duplicate(self) -> None:
        """Valid duplicate (same k and token) should return True."""
        result = check_duplicate_payword_payment(
            k=5, token="token1", prev_k=5, prev_token="token1"
        )
        assert result is True

    def test_check_duplicate_payword_payment_replay_attack_raises(self) -> None:
        """Duplicate k with different token should raise ValueError."""
        with pytest.raises(ValueError, match="mismatched token"):
            check_duplicate_payword_payment(
                k=5, token="token1", prev_k=5, prev_token="token2"
            )

    def test_check_duplicate_payword_payment_different_k(self) -> None:
        """Different k should return False."""
        result = check_duplicate_payword_payment(
            k=6, token="token1", prev_k=5, prev_token="token1"
        )
        assert result is False

    def test_check_duplicate_payword_payment_no_previous(self) -> None:
        """No previous payment should return False."""
        result = check_duplicate_payword_payment(
            k=1, token="token1", prev_k=0, prev_token=None
        )
        assert result is False
