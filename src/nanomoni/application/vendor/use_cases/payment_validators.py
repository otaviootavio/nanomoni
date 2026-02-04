"""Pure validation functions for signature-based payment processing.

These functions contain business logic validation rules that can be tested
in isolation without dependencies on repositories or infrastructure.
"""

from __future__ import annotations

from typing import Optional


def validate_payment_amount(
    new_amount: int,
    prev_amount: int,
    channel_amount: int,
) -> None:
    """Validate payment amount business rules. Pure function.

    Args:
        new_amount: The new cumulative owed amount
        prev_amount: The previous cumulative owed amount
        channel_amount: The total channel amount

    Raises:
        ValueError: If amount is not increasing or exceeds channel amount.
    """
    if new_amount < prev_amount:
        raise ValueError(
            f"Owed amount must be increasing. Got {new_amount}, expected > {prev_amount}"
        )
    if new_amount > channel_amount:
        raise ValueError(
            f"Owed amount {new_amount} exceeds payment channel amount {channel_amount}"
        )


def check_duplicate_payment(
    new_amount: int,
    new_signature: str,
    prev_amount: int,
    prev_signature: Optional[str],
) -> bool:
    """Check if payment is a valid duplicate (idempotency) or replay attack.

    Args:
        new_amount: The new cumulative owed amount
        new_signature: The new payment signature
        prev_amount: The previous cumulative owed amount
        prev_signature: The previous payment signature (None if no previous payment)

    Returns:
        True if this is a valid duplicate payment (same amount and signature)

    Raises:
        ValueError: If duplicate amount has mismatched signature (replay attack).
    """
    if prev_signature is None:
        return False

    if new_amount == prev_amount:
        if new_signature != prev_signature:
            raise ValueError(
                "Duplicate owed amount with mismatched signature (possible replay attack)"
            )
        return True

    return False


def validate_vendor_ownership(
    channel_vendor_key: str,
    vendor_key: str,
) -> None:
    """Validate that payment channel belongs to this vendor.

    Args:
        channel_vendor_key: The vendor public key from the channel
        vendor_key: The vendor's public key

    Raises:
        ValueError: If channel doesn't belong to this vendor.
    """
    if channel_vendor_key != vendor_key:
        raise ValueError("Payment channel is not for this vendor")
