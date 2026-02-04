"""Pure validation functions for PayWord channel opening.

These functions contain business logic validation rules that can be tested
in isolation without dependencies on repositories or infrastructure.
"""

from __future__ import annotations


def validate_payword_channel_fields(
    payword_root_b64: str | None,
    payword_unit_value: int | None,
    payword_max_k: int | None,
) -> None:
    """Validate that PayWord fields are present for channel opening.

    Raises:
        ValueError: If any required PayWord field is missing.
    """
    if payword_root_b64 is None or payword_unit_value is None or payword_max_k is None:
        raise ValueError("PayWord fields are required for PayWord channel opening")


def validate_payword_field_values(
    payword_unit_value: int,
    payword_max_k: int,
) -> None:
    """Validate PayWord field values are positive and max_k is an integer.

    Args:
        payword_unit_value: The unit value for PayWord payments
        payword_max_k: The maximum k value for PayWord chain

    Raises:
        ValueError: If unit_value is not positive, max_k is not an integer,
            or max_k is not positive.
    """
    if payword_unit_value <= 0:
        raise ValueError("payword_unit_value must be positive")
    if not isinstance(payword_max_k, int):
        raise ValueError("payword_max_k must be an integer")
    if payword_max_k <= 0:
        raise ValueError("payword_max_k must be positive")


def validate_payword_max_owed(
    max_owed: int,
    channel_amount: int,
) -> None:
    """Validate that PayWord max owed amount doesn't exceed channel amount.

    Args:
        max_owed: The maximum cumulative owed amount from PayWord chain
        channel_amount: The total channel amount

    Raises:
        ValueError: If max_owed exceeds channel_amount.
    """
    if max_owed > channel_amount:
        raise ValueError(
            "PayWord max owed exceeds channel amount "
            f"(max_owed={max_owed}, amount={channel_amount})"
        )
