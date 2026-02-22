"""PayTree Second Opt-based payment channel client operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.shared.paytree_second_opt_payloads import (
    PaytreeSecondOptOpenChannelRequestPayload,
)
from nanomoni.application.vendor.paytree_second_opt_dtos import (
    ReceivePaytreeSecondOptPaymentDTO,
)
from nanomoni.crypto.certificates import json_to_bytes, sign_bytes
from nanomoni.crypto.paytree import update_cache_with_siblings_and_path
from nanomoni.crypto.paytree_second_opt import PaytreeSecondOpt
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
    from nanomoni.envs.client_env import Settings


def init_commitment(
    settings: Settings,
    payment_count: int,
) -> tuple[PaytreeSecondOpt, str, int, int]:
    """Initialize PayTree Second Opt commitment and return related values."""
    unit_value = settings.client_paytree_unit_value
    max_i = (
        settings.client_paytree_max_i
        if settings.client_paytree_max_i is not None
        else payment_count
    )
    if max_i < payment_count:
        raise RuntimeError("CLIENT_PAYTREE_MAX_I must be >= CLIENT_PAYMENT_COUNT")
    paytree = PaytreeSecondOpt.create(max_i=max_i)
    return paytree, paytree.commitment_root_b64, unit_value, max_i


def build_open_payload(
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    channel_amount: int,
    root_b64: str,
    unit_value: int,
    max_i: int,
) -> PaytreeSecondOptOpenChannelRequestPayload:
    """Build the open channel payload for PayTree Second Opt mode."""
    return PaytreeSecondOptOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=channel_amount,
        paytree_second_opt_root_b64=root_b64,
        paytree_second_opt_unit_value=unit_value,
        paytree_second_opt_max_i=max_i,
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
    """Build and sign open channel request DTO for PayTree Second Opt mode."""
    payload = PaytreeSecondOptOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        paytree_second_opt_root_b64=root_b64,
        paytree_second_opt_unit_value=unit_value,
        paytree_second_opt_max_i=max_i,
    )
    payload_bytes = json_to_bytes(payload.model_dump())
    signature_b64 = sign_bytes(client_private_key, payload_bytes)

    return OpenChannelRequestDTO(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        open_signature_b64=signature_b64,
        paytree_second_opt_root_b64=root_b64,
        paytree_second_opt_unit_value=unit_value,
        paytree_second_opt_max_i=max_i,
    )


async def send_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    paytree: PaytreeSecondOpt,
    payments: list[int],
) -> None:
    """Send PayTree Second Opt payments with sequentially pruned proofs."""
    node_cache_b64: dict[str, str] = {}
    for i in payments:
        i_val, leaf_b64, siblings_b64, full_siblings_b64 = (
            paytree.payment_proof_with_full_siblings(i=i, node_cache_b64=node_cache_b64)
        )
        await vendor.send_paytree_second_opt_payment(
            channel_id,
            ReceivePaytreeSecondOptPaymentDTO(
                i=i_val,
                max_i=paytree.max_i,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
            ),
        )
        if (
            update_cache_with_siblings_and_path(
                i=i_val,
                leaf_b64=leaf_b64,
                full_siblings_b64=full_siblings_b64,
                node_cache_b64=node_cache_b64,
            )
            is None
        ):
            raise RuntimeError("Failed to update PayTree Second Opt node cache")
