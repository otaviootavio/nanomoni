"""PayTree-based payment channel client operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nanomoni.application.shared.paytree_payloads import (
    PaytreeOpenChannelRequestPayload,
)
from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.vendor.paytree_dtos import ReceivePaytreePaymentDTO
from nanomoni.crypto.paytree import Paytree
from nanomoni.crypto.certificates import (
    json_to_bytes,
    sign_bytes,
)
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

if TYPE_CHECKING:
    from nanomoni.envs.client_env import Settings
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey


def init_commitment(
    settings: Settings,
    payment_count: int,
) -> tuple[Paytree, str, int, int]:
    """Initialize PayTree commitment and return related values.

    PayTree mode:
    - Each payment sends an index i; the money owed is cumulative_owed_amount = i * unit_value.
    - max_i is part of the channel commitment (persisted/enforced by vendor + issuer).
      We default max_i to payment_count for convenience, but they are different concepts:
      payment_count = how many payments this run; max_i = channel capacity in steps.
    - The channel amount must cover the maximum possible owed amount:
      (max_i * unit_value) <= channel_amount  (issuer validates this at open).

    Args:
        settings: Client settings containing PayTree configuration
        payment_count: Number of payments to send

    Returns:
        Tuple of (Paytree instance, root_b64, unit_value, max_i)

    Raises:
        RuntimeError: If max_i < payment_count
    """
    paytree_unit_value = settings.client_paytree_unit_value
    paytree_max_i = (
        settings.client_paytree_max_i
        if settings.client_paytree_max_i is not None
        else payment_count
    )
    if paytree_max_i < payment_count:
        raise RuntimeError("CLIENT_PAYTREE_MAX_I must be >= CLIENT_PAYMENT_COUNT")
    paytree = Paytree.create(max_i=paytree_max_i)
    paytree_root_b64 = paytree.commitment_root_b64
    return paytree, paytree_root_b64, paytree_unit_value, paytree_max_i


def build_open_payload(
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    channel_amount: int,
    paytree_root_b64: str,
    paytree_unit_value: int,
    paytree_max_i: int,
) -> PaytreeOpenChannelRequestPayload:
    """Build the open channel payload for PayTree mode.

    Args:
        client_public_key_der_b64: Client's public key in DER base64 format
        vendor_public_key_der_b64: Vendor's public key in DER base64 format
        channel_amount: Amount to lock in the channel
        paytree_root_b64: PayTree commitment root in base64
        paytree_unit_value: Unit value for each payment step
        paytree_max_i: Maximum i value (channel capacity in steps)

    Returns:
        The PayTree open channel request payload.
    """
    return PaytreeOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=channel_amount,
        paytree_root_b64=paytree_root_b64,
        paytree_unit_value=paytree_unit_value,
        paytree_max_i=paytree_max_i,
    )


def build_open_channel_request(
    client_private_key: EllipticCurvePrivateKey,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    amount: int,
    paytree_root_b64: str,
    paytree_unit_value: int,
    paytree_max_i: int,
) -> OpenChannelRequestDTO:
    """Build and sign open channel request DTO for PayTree mode.

    Args:
        client_private_key: Client's private key for signing
        client_public_key_der_b64: Client's public key in DER base64 format
        vendor_public_key_der_b64: Vendor's public key in DER base64 format
        amount: Amount to lock in the channel
        paytree_root_b64: PayTree commitment root in base64
        paytree_unit_value: Unit value for each payment step
        paytree_max_i: Maximum i value (channel capacity in steps)

    Returns:
        Signed OpenChannelRequestDTO with flat fields.
    """
    payload = PaytreeOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        paytree_root_b64=paytree_root_b64,
        paytree_unit_value=paytree_unit_value,
        paytree_max_i=paytree_max_i,
    )
    payload_bytes = json_to_bytes(payload.model_dump())
    signature_b64 = sign_bytes(client_private_key, payload_bytes)

    return OpenChannelRequestDTO(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        open_signature_b64=signature_b64,
        paytree_root_b64=paytree_root_b64,
        paytree_unit_value=paytree_unit_value,
        paytree_max_i=paytree_max_i,
    )


async def send_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    paytree: Paytree,
    payments: list[int],
) -> None:
    """Send PayTree payments to the vendor, generating proofs on-demand.

    Note: We generate proofs on-demand in the loop rather than precomputing them.
    In our experiments, precomputing all PayTree proofs (i, leaf_b64, siblings_b64[])
    did not improve TPS but caused significant memory growth, especially for large
    payment counts. The siblings_b64 arrays can be large (O(log n) per proof).
    Although the tree leaves are still loaded in memory (as part of the Paytree
    object), generating proofs on-demand reduces peak memory usage.

    Args:
        vendor: The vendor client instance
        channel_id: The channel computed ID
        paytree: The PayTree instance
        payments: List of i index values (monotonic sequence)
    """
    for i in payments:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)
        await vendor.send_paytree_payment(
            channel_id,
            ReceivePaytreePaymentDTO(
                i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
            ),
        )
