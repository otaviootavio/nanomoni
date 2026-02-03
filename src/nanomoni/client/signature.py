"""Signature-based payment channel client operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nanomoni.application.shared.payment_channel_payloads import (
    SignatureChannelPaymentPayload,
    OpenChannelRequestPayload,
)
from nanomoni.application.vendor.dtos import ReceivePaymentDTO
from nanomoni.crypto.certificates import Envelope, generate_envelope
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey


def build_open_payload(
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    channel_amount: int,
) -> OpenChannelRequestPayload:
    """Build the open channel payload for signature mode.

    Args:
        client_public_key_der_b64: Client's public key in DER base64 format
        vendor_public_key_der_b64: Vendor's public key in DER base64 format
        channel_amount: Amount to lock in the channel

    Returns:
        The open channel request payload.
    """
    return OpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=channel_amount,
    )


def prepare_payments(
    channel_id: str,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    client_private_key: EllipticCurvePrivateKey,
    payments: list[int],
) -> list[ReceivePaymentDTO]:
    """Precompute signed payment envelopes for signature mode.

    Precomputing signed envelopes before sending requests ensures the runtime path
    measures mostly network + server-side verification (fairer vs payword pre-hashing).

    Args:
        channel_id: The channel ID
        client_public_key_der_b64: Client's public key in DER base64 format
        vendor_public_key_der_b64: Vendor's public key in DER base64 format
        client_private_key: Client's private key for signing
        payments: List of cumulative_owed_amount values (monotonic sequence)

    Returns:
        List of ReceivePaymentDTO with pre-signed envelopes.
    """
    signed_payment_envs: list[Envelope] = []
    for cumulative_owed_amount in payments:
        tx_payload = SignatureChannelPaymentPayload(
            channel_id=channel_id,
            cumulative_owed_amount=cumulative_owed_amount,
        )
        signed_payment_envs.append(
            generate_envelope(client_private_key, tx_payload.model_dump())
        )

    return [ReceivePaymentDTO(envelope=pay_env) for pay_env in signed_payment_envs]


async def send_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    payment_dtos: list[ReceivePaymentDTO],
) -> None:
    """Send pre-signed payment envelopes to the vendor.

    Args:
        vendor: The vendor client instance
        channel_id: The channel ID
        payment_dtos: List of pre-signed payment DTOs
    """
    for pay_dto in payment_dtos:
        await vendor.send_off_chain_payment(channel_id, pay_dto)
