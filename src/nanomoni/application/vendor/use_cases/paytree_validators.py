"""Pure validation functions for PayTree payment processing.

These functions contain business logic validation rules that can be tested
in isolation without dependencies on repositories or infrastructure.
"""

from __future__ import annotations

from typing import Optional


def validate_paytree_i(
    i: int,
    prev_i: int,
    max_i: int,
) -> None:
    """Validate PayTree i business rules. Pure function.

    Args:
        i: The new i value
        prev_i: The previous i value (0 if no previous payment)
        max_i: The maximum allowed i value for the channel

    Raises:
        ValueError: If i is not increasing or exceeds max_i.
    """
    if i <= prev_i:
        raise ValueError(f"PayTree i must be increasing. Got {i}, expected > {prev_i}")
    if i > max_i:
        raise ValueError("PayTree i exceeds channel max_i")


def validate_paytree_amount(
    cumulative_owed: int,
    channel_amount: int,
) -> None:
    """Validate that PayTree cumulative owed amount doesn't exceed channel amount.

    Args:
        cumulative_owed: The cumulative owed amount from PayTree
        channel_amount: The total channel amount

    Raises:
        ValueError: If cumulative_owed exceeds channel_amount.
    """
    if cumulative_owed > channel_amount:
        raise ValueError(
            f"cumulative_owed_amount {cumulative_owed} exceeds payment channel amount {channel_amount}"
        )


def check_duplicate_paytree_payment(
    i: int,
    leaf: str,
    siblings: list[str],
    prev_i: int,
    prev_leaf: Optional[str],
    prev_siblings: Optional[list[str]],
) -> bool:
    """Check if PayTree payment is a valid duplicate (idempotency) or replay attack.

    Args:
        i: The new i value
        leaf: The new leaf (base64)
        siblings: The new siblings list (base64)
        prev_i: The previous i value (0 if no previous payment)
        prev_leaf: The previous leaf (None if no previous payment)
        prev_siblings: The previous siblings (None if no previous payment)

    Returns:
        True if this is a valid duplicate payment (same i, leaf, and siblings)

    Raises:
        ValueError: If duplicate i has mismatched proof (replay attack).
    """
    if prev_leaf is None or prev_siblings is None:
        return False

    if i == prev_i:
        if leaf != prev_leaf or siblings != prev_siblings:
            raise ValueError(
                "Duplicate PayTree i with mismatched proof (possible replay attack)"
            )
        return True

    return False
