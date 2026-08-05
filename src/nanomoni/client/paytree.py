"""PayTree-based payment channel client operations."""

from __future__ import annotations

from asyncio import sleep
from time import perf_counter

from nanomoni.application.shared.paytree_payloads import (
    PaytreeOpenChannelRequestPayload,
)
from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.vendor.paytree_dtos import (
    ReceivePaytreeStdPaymentDTO,
    ReceivePaytreeFirstOptPaymentDTO,
)
from nanomoni.crypto.paytree import Paytree
from nanomoni.crypto.certificates import (
    json_to_bytes,
    sign_bytes,
)
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync
from nanomoni.envs.client_env import Settings
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey


def init_commitment(
    settings: Settings,
    payment_count: int,
) -> tuple[Paytree, str, int, int]:
    """Initialize PayTree commitment and return related values."""
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
    payload = PaytreeOpenChannelRequestPayload(
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=amount,
        paytree_root_b64=paytree_root_b64,
        paytree_unit_value=paytree_unit_value,
        paytree_max_i=paytree_max_i,
    )
    payload_bytes = json_to_bytes(payload.model_dump(exclude_none=True))
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


async def send_std_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    paytree: Paytree,
    payments: list[int],
    inter_payment_delay: float = 0.0,
) -> None:
    """Send standard (full-proof) PayTree payments to the vendor.

    ``inter_payment_delay`` controls the pause between successive network calls;
    used by the benchmark client to achieve a fixed request rate.

    Note: We generate proofs on-demand in the loop rather than precomputing them.
    In our experiments, precomputing all PayTree proofs (i, leaf_b64, siblings_b64[])
    did not improve TPS but caused significant memory growth, especially for large
    payment counts. The siblings_b64 arrays can be large (O(log n) per proof).
    Although the tree leaves are still loaded in memory (as part of the Paytree
    object), generating proofs on-demand reduces peak memory usage.
    """
    start = perf_counter()
    for n, i in enumerate(payments):
        if inter_payment_delay > 0:
            target = start + n * inter_payment_delay
            now = perf_counter()
            if target > now:
                await sleep(target - now)
            elif now - target > inter_payment_delay:
                # Fell behind by more than one slot (e.g. a stalled request) -
                # resync the schedule instead of letting later iterations fire
                # back-to-back to "catch up", which would burst well above the
                # configured rate and contaminate steady-state measurements.
                start = now - n * inter_payment_delay
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)
        await vendor.send_paytree_std_payment(
            channel_id,
            ReceivePaytreeStdPaymentDTO(
                i=i_val,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
            ),
        )


async def send_first_opt_payments(
    vendor: VendorClientAsync,
    channel_id: str,
    paytree: Paytree,
    payments: list[int],
    inter_payment_delay: float = 0.0,
) -> None:
    """Send first-opt (pruned-proof) PayTree payments to the vendor."""
    prior_sent_indexes: list[int] = []
    start = perf_counter()
    for n, i in enumerate(payments):
        if inter_payment_delay > 0:
            target = start + n * inter_payment_delay
            now = perf_counter()
            if target > now:
                await sleep(target - now)
            elif now - target > inter_payment_delay:
                start = now - n * inter_payment_delay
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(
            i, prior_sent_indexes
        )
        prior_sent_indexes.append(i)
        await vendor.send_paytree_first_opt_payment(
            channel_id,
            ReceivePaytreeFirstOptPaymentDTO(
                i=i_val,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
                paytree_max_i=paytree.max_i,
            ),
        )
