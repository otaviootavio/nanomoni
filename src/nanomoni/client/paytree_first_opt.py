"""PayTree First Opt-based payment channel client operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.shared.paytree_first_opt_payloads import (
    PaytreeFirstOptOpenChannelRequestPayload,
)
from nanomoni.application.vendor.paytree_first_opt_dtos import (
    ReceivePaytreeFirstOptPaymentDTO,
)
from nanomoni.crypto.certificates import json_to_bytes, sign_bytes
from nanomoni.crypto.paytree_first_opt import PaytreeFirstOpt
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
    from nanomoni.envs.client_env import Settings


def init_commitment(
    settings: Settings,
    payment_count: int,
) -> tuple[PaytreeFirstOpt, str, int, int]:
    """Initialize PayTree First Opt commitment and return related values."""
    unit_value = settings.client_paytree_unit_value
    max_i = (
        settings.client_paytree_max_i
        if settings.client_paytree_max_i is not None
        else payment_count
    )
    if max_i < payment_count:
        raise RuntimeError("CLIENT_PAYTREE_MAX_I must be >= CLIENT_PAYMENT_COUNT")
    paytree = PaytreeFirstOpt.create(max_i=max_i)
    return paytree, paytree.commitment_root_b64, unit_value, max_i


def build_open_payload(
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    channel_amount: int,
    root_b64: str,
    unit_value: int,
    max_i: int,
) -> PaytreeFirstOptOpenChannelRequestPayload:
    """Build the open channel payload for PayTree First Opt mode."""
    return PaytreeFirstOptOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=channel_amount,
        paytree_first_opt_root_b64=root_b64,
        paytree_first_opt_unit_value=unit_value,
        paytree_first_opt_max_i=max_i,
    )


def build_open_channel_request(
    client_private_key: EllipticCurvePrivateKey,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    amount: int,
    root_b64: str,
    unit_value: int,
    max_i: int,
) -> OpenChannelRequestDTO:
    """Build and sign open channel request DTO for PayTree First Opt mode."""
    payload = PaytreeFirstOptOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        paytree_first_opt_root_b64=root_b64,
        paytree_first_opt_unit_value=unit_value,
        paytree_first_opt_max_i=max_i,
    )
    payload_bytes = json_to_bytes(payload.model_dump())
    signature_b64 = sign_bytes(client_private_key, payload_bytes)

    return OpenChannelRequestDTO(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        open_signature_b64=signature_b64,
        paytree_first_opt_root_b64=root_b64,
        paytree_first_opt_unit_value=unit_value,
        paytree_first_opt_max_i=max_i,
    )


async def send_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    paytree: PaytreeFirstOpt,
    payments: list[int],
) -> None:
    """Send PayTree First Opt payments with sequentially pruned proofs."""
    last_verified_index: Optional[int] = None
    for i in payments:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(
            i=i, last_verified_index=last_verified_index
        )
        await vendor.send_paytree_first_opt_payment(
            channel_id,
            ReceivePaytreeFirstOptPaymentDTO(
                i=i_val,
                max_i=paytree.max_i,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
            ),
        )
        last_verified_index = i_val
