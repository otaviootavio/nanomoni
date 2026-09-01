"""Shared scenario for asserting Merkle node-store growth per PayTree payment.

Runs the *same* sequence of real payments through the real service +
``MerkleNodeRepositoryImpl`` for both first-opt (P only) and second-opt
(P + Q) schemes, against whatever ``KeyValueStore`` the caller wires up --
fakeredis (fast, no services) or real Redis (integration tier). Both tiers
exercise this one scenario so a store-specific bug can't silently diverge
from the fakeredis-only story.

Node counts come from ``MerkleNodeRepositoryImpl.count_nodes``, backed by
the same ``merkle_node_index`` ZSET the repository already maintains for
``delete()`` -- membership is deduplicated by Redis itself (ZADD is
idempotent), so a count taken after each payment reflects distinct node
keys ever written, exactly the "sparse vs. dense" storage claim first-opt
and second-opt make about themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NoReturn, Union

from nanomoni.application.shared.paytree_scheme import (
    PaytreeFirstOptCryptoScheme,
    PaytreeSecondOptCryptoScheme,
)
from nanomoni.application.vendor.paytree_dtos import ReceivePaytreeFirstOptPaymentDTO
from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)
from nanomoni.application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
)
from nanomoni.crypto.paytree import Paytree
from nanomoni.domain.shared.proof_reference import PaymentScheme
from nanomoni.domain.vendor.entities import PaymentChannel
from nanomoni.infrastructure.storage import KeyValueStore
from nanomoni.infrastructure.vendor.merkle_node_repository_impl import (
    MerkleNodeRepositoryImpl,
)
from nanomoni.infrastructure.vendor.payment_repository_impl import (
    PaymentRepositoryImpl,
)

MAX_STEPS = 7  # 8 leaves (i=0 unused as a first payment); depth 3
DEPTH = 3


def _unexpected_issuer_client_factory() -> NoReturn:
    raise AssertionError(
        "issuer should not be contacted: the channel is pre-seeded directly "
        "in the node repo, so receive_payment's fast path must find it there"
    )


async def _seed_channel(
    store: KeyValueStore, channel_id: str, commitment_b64: str
) -> None:
    channel = PaymentChannel(
        channel_id=channel_id,
        client_public_key_der_b64="client",
        vendor_public_key_der_b64="vendor",
        salt_b64="salt",
        amount=10_000,
        balance=0,
        is_closed=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        commitment=commitment_b64,
        scheme=PaymentScheme.PAYTREE,
        max_steps=MAX_STEPS,
        unit_value=1,
        last_proof_reference=None,
    )
    await store.set(f"payment_channel:{channel_id}", channel.model_dump_json())


async def run_node_storage_scenario(
    store: KeyValueStore,
    channel_id: str,
    *,
    second_opt: bool,
    indices: list[int],
    seed: bytes,
) -> list[int]:
    """Drive ``indices`` as sequential payments; return the node-store count
    (``count_nodes``) observed right after each one, in order."""
    paytree = Paytree.create(max_i=MAX_STEPS, seed=seed)

    payment_repository = PaymentRepositoryImpl(store)
    await _seed_channel(store, channel_id, paytree.commitment_root_b64)

    node_repo = MerkleNodeRepositoryImpl(store)
    service: Union[PaytreeFirstOptPaymentService, PaytreeSecondOptPaymentService]
    if second_opt:
        service = PaytreeSecondOptPaymentService(
            payment_repository=payment_repository,
            issuer_client_factory=_unexpected_issuer_client_factory,
            vendor_public_key_der_b64="vendor",
            crypto_scheme=PaytreeSecondOptCryptoScheme(),
            node_repo=node_repo,
        )
    else:
        service = PaytreeFirstOptPaymentService(
            payment_repository=payment_repository,
            issuer_client_factory=_unexpected_issuer_client_factory,
            vendor_public_key_der_b64="vendor",
            crypto_scheme=PaytreeFirstOptCryptoScheme(),
            node_repo=node_repo,
        )

    counts: list[int] = []
    prior_sent: list[int] = []
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(i, prior_sent)
        await service.receive_payment(
            channel_id,
            ReceivePaytreeFirstOptPaymentDTO(
                i=i_val,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
                paytree_max_i=MAX_STEPS,
            ),
        )
        prior_sent.append(i)
        counts.append(await node_repo.count_nodes(channel_id))

    return counts
