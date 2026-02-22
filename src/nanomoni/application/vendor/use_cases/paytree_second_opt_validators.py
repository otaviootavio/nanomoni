"""Pure validation functions for PayTree Second Opt payment processing."""

from __future__ import annotations

from typing import Optional


def validate_paytree_second_opt_i(i: int, prev_i: int, max_i: int) -> None:
    """Validate PayTree Second Opt i business rules."""
    if i <= prev_i:
        raise ValueError(
            f"PayTree Second Opt i must be increasing. Got {i}, expected > {prev_i}"
        )
    if i > max_i:
        raise ValueError("PayTree Second Opt i exceeds channel max_i")


def validate_paytree_second_opt_amount(
    cumulative_owed: int, channel_amount: int
) -> None:
    """Validate cumulative owed amount doesn't exceed channel amount."""
    if cumulative_owed > channel_amount:
        raise ValueError(
            f"cumulative_owed_amount {cumulative_owed} exceeds payment channel amount {channel_amount}"
        )


def check_duplicate_paytree_second_opt_payment(
    i: int,
    leaf: str,
    siblings: list[str],
    prev_i: int,
    prev_leaf: Optional[str],
    prev_siblings: Optional[list[str]],
) -> bool:
    """Check if payment is a valid duplicate (idempotency) or replay."""
    if prev_leaf is None or prev_siblings is None:
        return False
    if i == prev_i:
        if leaf != prev_leaf or siblings != prev_siblings:
            raise ValueError(
                "Duplicate PayTree Second Opt i with mismatched proof (possible replay attack)"
            )
        return True
    return False
