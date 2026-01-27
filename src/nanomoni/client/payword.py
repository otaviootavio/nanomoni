"""PayWord-based payment channel client operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nanomoni.application.shared.payword_payloads import (
    PaywordOpenChannelRequestPayload,
)
from nanomoni.application.vendor.payword_dtos import ReceivePaywordPaymentDTO
from nanomoni.crypto.payword import Payword
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

if TYPE_CHECKING:
    from nanomoni.envs.client_env import Settings


def init_commitment(
    settings: Settings,
    payment_count: int,
) -> tuple[Payword, str, int, int]:
    """Initialize PayWord commitment and return related values.

    PayWord mode:
    - Each payment sends a counter k; the money owed is cumulative_owed_amount = k * unit_value.
    - max_k is part of the channel commitment (persisted/enforced by vendor + issuer).
      We default max_k to payment_count for convenience, but they are different concepts:
      payment_count = how many payments this run; max_k = channel capacity in steps.
    - The channel amount must cover the maximum possible owed amount:
      (max_k * unit_value) <= channel_amount  (issuer validates this at open).

    Args:
        settings: Client settings containing PayWord configuration
        payment_count: Number of payments to send

    Returns:
        Tuple of (Payword instance, root_b64, unit_value, max_k)

    Raises:
        RuntimeError: If max_k < payment_count
    """
    payword_unit_value = settings.client_payword_unit_value
    payword_max_k = settings.client_payword_max_k or payment_count
    if payword_max_k < payment_count:
        raise RuntimeError("CLIENT_PAYWORD_MAX_K must be >= CLIENT_PAYMENT_COUNT")
    # Always use pebbling optimization in clients (trade memory for hashing).
    PAYWORD_PEBBLE_COUNT = payword_max_k
    payword = Payword.create(max_k=payword_max_k, pebble_count=PAYWORD_PEBBLE_COUNT)
    payword_root_b64 = payword.commitment_root_b64
    return payword, payword_root_b64, payword_unit_value, payword_max_k


def build_open_payload(
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    channel_amount: int,
    payword_root_b64: str,
    payword_unit_value: int,
    payword_max_k: int,
) -> PaywordOpenChannelRequestPayload:
    """Build the open channel payload for PayWord mode.

    Args:
        client_public_key_der_b64: Client's public key in DER base64 format
        vendor_public_key_der_b64: Vendor's public key in DER base64 format
        channel_amount: Amount to lock in the channel
        payword_root_b64: PayWord commitment root in base64
        payword_unit_value: Unit value for each payment step
        payword_max_k: Maximum k value (channel capacity in steps)

    Returns:
        The PayWord open channel request payload.
    """
    return PaywordOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=channel_amount,
        payword_root_b64=payword_root_b64,
        payword_unit_value=payword_unit_value,
        payword_max_k=payword_max_k,
    )


async def send_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    payword: Payword,
    payments: list[int],
) -> None:
    """Send PayWord payments to the vendor, generating proofs on-demand.

    Note: We generate proofs on-demand in the loop rather than precomputing them.
    Since the Payword object already stores the complete hash chain, precomputing
    all proofs is redundant and increases memory usage unnecessarily.

    Args:
        vendor: The vendor client instance
        channel_id: The channel ID
        payword: The PayWord instance
        payments: List of k counter values (monotonic sequence)
    """
    for k in payments:
        token_b64 = payword.payment_proof_b64(k=k)
        await vendor.send_payword_payment(
            channel_id,
            ReceivePaywordPaymentDTO(k=k, token_b64=token_b64),
        )
