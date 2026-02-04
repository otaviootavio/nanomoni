"""Helpers for tampering with cryptographic data in E2E tests."""

from __future__ import annotations

import base64

from nanomoni.application.vendor.dtos import ReceivePaymentDTO


def tamper_b64_preserve_validity(b64: str) -> str:
    """
    Tamper with a base64 string while preserving base64 validity.

    Decodes the base64, flips one bit in the first byte, and re-encodes.
    This ensures the result is still valid base64 but the content is corrupted.

    Args:
        b64: Base64-encoded string to tamper with

    Returns:
        Tampered base64 string (still valid base64, but content is corrupted)
    """
    try:
        decoded = base64.b64decode(b64, validate=True)
        if len(decoded) == 0:
            # Can't tamper empty data, return as-is
            return b64
        # Flip the least significant bit of the first byte
        tampered_bytes = bytearray(decoded)
        tampered_bytes[0] ^= 1
        return base64.b64encode(bytes(tampered_bytes)).decode("utf-8")
    except Exception:
        # If decoding fails, return original (shouldn't happen in tests)
        return b64


def tamper_payment_dto_signature(payment_dto: ReceivePaymentDTO) -> ReceivePaymentDTO:
    """
    Create a tampered version of a payment DTO with corrupted signature.

    Args:
        payment_dto: Original payment DTO

    Returns:
        New payment DTO with tampered signature_b64
    """
    return ReceivePaymentDTO(
        channel_id=payment_dto.channel_id,
        cumulative_owed_amount=payment_dto.cumulative_owed_amount,
        signature_b64=tamper_b64_preserve_validity(payment_dto.signature_b64),
    )
