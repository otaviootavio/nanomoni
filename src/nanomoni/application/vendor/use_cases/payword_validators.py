"""Pure validation functions for PayWord payment processing.

These functions contain business logic validation rules that can be tested
in isolation without dependencies on repositories or infrastructure.
"""

from __future__ import annotations

from typing import Optional


def validate_payword_k(
    k: int,
    prev_k: int,
    max_k: int,
) -> None:
    """Validate PayWord k business rules. Pure function.

    Args:
        k: The new k value
        prev_k: The previous k value (0 if no previous payment)
        max_k: The maximum allowed k value for the channel

    Raises:
        ValueError: If k is not increasing or exceeds max_k.
    """
    if k <= prev_k:
        raise ValueError(f"PayWord k must be increasing. Got {k}, expected > {prev_k}")
    if k > max_k:
        raise ValueError("PayWord k exceeds channel max_k")


def validate_payword_amount(
    cumulative_owed: int,
    channel_amount: int,
) -> None:
    """Validate that PayWord cumulative owed amount doesn't exceed channel amount.

    Args:
        cumulative_owed: The cumulative owed amount from PayWord chain
        channel_amount: The total channel amount

    Raises:
        ValueError: If cumulative_owed exceeds channel_amount.
    """
    if cumulative_owed > channel_amount:
        raise ValueError(
            f"Owed amount {cumulative_owed} exceeds payment channel amount {channel_amount}"
        )


def check_duplicate_payword_payment(
    k: int,
    token: str,
    prev_k: int,
    prev_token: Optional[str],
) -> bool:
    """Check if PayWord payment is a valid duplicate (idempotency) or replay attack.

    Args:
        k: The new k value
        token: The new token (base64)
        prev_k: The previous k value (0 if no previous payment)
        prev_token: The previous token (None if no previous payment)

    Returns:
        True if this is a valid duplicate payment (same k and token)

    Raises:
        ValueError: If duplicate k has mismatched token (replay attack).
    """
    if prev_token is None:
        return False

    if k == prev_k:
        if token != prev_token:
            raise ValueError(
                "Duplicate PayWord k with mismatched token (possible replay attack)"
            )
        return True

    return False
