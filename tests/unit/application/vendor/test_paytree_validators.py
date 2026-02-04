"""Unit tests for PayTree validators (pure functions)."""

import pytest

from nanomoni.application.vendor.use_cases.paytree_validators import (
    validate_paytree_i,
    validate_paytree_amount,
    check_duplicate_paytree_payment,
)


class TestValidatePaytreeI:
    """Test validate_paytree_i function."""

    def test_validate_paytree_i_increasing(self) -> None:
        """PayTree i must be strictly increasing."""
        validate_paytree_i(i=5, prev_i=3, max_i=10)
        # Should not raise

    def test_validate_paytree_i_decreasing_raises(self) -> None:
        """Decreasing i should raise ValueError."""
        with pytest.raises(ValueError, match="must be increasing"):
            validate_paytree_i(i=2, prev_i=3, max_i=10)

    def test_validate_paytree_i_equal_raises(self) -> None:
        """Equal i should raise ValueError (must be strictly increasing)."""
        with pytest.raises(ValueError, match="must be increasing"):
            validate_paytree_i(i=3, prev_i=3, max_i=10)

    def test_validate_paytree_i_exceeds_max_raises(self) -> None:
        """i exceeding max_i should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds channel max_i"):
            validate_paytree_i(i=11, prev_i=3, max_i=10)

    def test_validate_paytree_i_at_max_limit(self) -> None:
        """i equal to max_i should be valid."""
        validate_paytree_i(i=10, prev_i=3, max_i=10)
        # Should not raise

    def test_validate_paytree_i_first_payment(self) -> None:
        """First payment (prev_i=0) should be valid."""
        validate_paytree_i(i=1, prev_i=0, max_i=10)
        # Should not raise


class TestValidatePaytreeAmount:
    """Test validate_paytree_amount function."""

    def test_validate_paytree_amount_within_limit(self) -> None:
        """Amount within channel limit should be valid."""
        validate_paytree_amount(cumulative_owed=500, channel_amount=1000)
        # Should not raise

    def test_validate_paytree_amount_exceeds_channel_raises(self) -> None:
        """Amount exceeding channel should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds payment channel amount"):
            validate_paytree_amount(cumulative_owed=1500, channel_amount=1000)

    def test_validate_paytree_amount_at_channel_limit(self) -> None:
        """Amount equal to channel limit should be valid."""
        validate_paytree_amount(cumulative_owed=1000, channel_amount=1000)
        # Should not raise


class TestCheckDuplicatePaytreePayment:
    """Test check_duplicate_paytree_payment function."""

    def test_check_duplicate_paytree_payment_valid_duplicate(self) -> None:
        """Valid duplicate (same i, leaf, and siblings) should return True."""
        result = check_duplicate_paytree_payment(
            i=5,
            leaf="leaf1",
            siblings=["sib1", "sib2"],
            prev_i=5,
            prev_leaf="leaf1",
            prev_siblings=["sib1", "sib2"],
        )
        assert result is True

    def test_check_duplicate_paytree_payment_replay_attack_raises(self) -> None:
        """Duplicate i with different proof should raise ValueError."""
        with pytest.raises(ValueError, match="mismatched proof"):
            check_duplicate_paytree_payment(
                i=5,
                leaf="leaf1",
                siblings=["sib1", "sib2"],
                prev_i=5,
                prev_leaf="leaf2",
                prev_siblings=["sib1", "sib2"],
            )

    def test_check_duplicate_paytree_payment_different_siblings_raises(self) -> None:
        """Duplicate i with different siblings should raise ValueError."""
        with pytest.raises(ValueError, match="mismatched proof"):
            check_duplicate_paytree_payment(
                i=5,
                leaf="leaf1",
                siblings=["sib1", "sib2"],
                prev_i=5,
                prev_leaf="leaf1",
                prev_siblings=["sib1", "sib3"],
            )

    def test_check_duplicate_paytree_payment_different_i(self) -> None:
        """Different i should return False."""
        result = check_duplicate_paytree_payment(
            i=6,
            leaf="leaf1",
            siblings=["sib1", "sib2"],
            prev_i=5,
            prev_leaf="leaf1",
            prev_siblings=["sib1", "sib2"],
        )
        assert result is False

    def test_check_duplicate_paytree_payment_no_previous(self) -> None:
        """No previous payment should return False."""
        result = check_duplicate_paytree_payment(
            i=1,
            leaf="leaf1",
            siblings=["sib1"],
            prev_i=0,
            prev_leaf=None,
            prev_siblings=None,
        )
        assert result is False
