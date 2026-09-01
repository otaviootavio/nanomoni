"""Integration: second-opt receive_payment persists computed (Q) nodes too.

PaytreeSecondOptPaymentService is a standalone class (independent of
PaytreeFirstOptPaymentService -- no shared base class), using
PaytreeSecondOptCryptoScheme for verification and node-store writes. Earlier
steps tested the Q-storage mechanism at the crypto/protocol layer and
directly against PaytreeSecondOptCryptoScheme's methods; this test drives
real payments through the service against a real MerkleNodeRepositoryImpl
(backed by fakeredis), to confirm the Q-storage path actually persists
through the full use case, not just in principle -- the computed ancestor
hashes land in the repository, not just inside the in-memory computed_path
returned during verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NoReturn

import pytest

from nanomoni.application.shared.paytree_scheme import PaytreeSecondOptCryptoScheme
from nanomoni.application.vendor.paytree_dtos import ReceivePaytreeFirstOptPaymentDTO
from nanomoni.application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
)
from nanomoni.crypto.merkle_index import get_ancestor_at_level, key_eytzinger
from nanomoni.crypto.paytree import Paytree, bytes_to_b64
from nanomoni.domain.shared.proof_reference import PaymentScheme
from nanomoni.domain.vendor.entities import PaymentChannel
from nanomoni.infrastructure.vendor.merkle_node_repository_impl import (
    MerkleNodeRepositoryImpl,
)
from tests.fixtures.in_memory_repositories import (
    create_vendor_payment_repositories,
    initialize_vendor_payment_repositories,
)
from tests.fixtures.in_memory_storage import InMemoryKeyValueStore

MAX_STEPS = 7  # 8 leaves (i=0 unused -- rejected as a first payment); depth 3
DEPTH = 3
CHANNEL_ID = "computed-path-storage-channel"


def _unexpected_issuer_client_factory() -> NoReturn:
    raise AssertionError(
        "issuer should not be contacted: the channel is pre-seeded directly "
        "in the node repo, so receive_payment's fast path must find it there"
    )


async def _seed_channel(store: InMemoryKeyValueStore, commitment_b64: str) -> None:
    channel = PaymentChannel(
        channel_id=CHANNEL_ID,
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
    await store.set(f"payment_channel:{CHANNEL_ID}", channel.model_dump_json())


@pytest.mark.asyncio
async def test_receive_payment_persists_computed_path_alongside_received_siblings() -> (
    None
):
    paytree = Paytree.create(max_i=MAX_STEPS, seed=b"computed-path-storage-test")
    tree_levels = paytree._tree_levels

    repos = create_vendor_payment_repositories()
    await initialize_vendor_payment_repositories(repos)
    await _seed_channel(repos.store, paytree.commitment_root_b64)

    node_repo = MerkleNodeRepositoryImpl(repos.store)
    service = PaytreeSecondOptPaymentService(
        payment_repository=repos.payment,
        issuer_client_factory=_unexpected_issuer_client_factory,
        vendor_public_key_der_b64="vendor",
        crypto_scheme=PaytreeSecondOptCryptoScheme(),
        node_repo=node_repo,
    )

    # Payment 1: i=1, no prior payments -> full pruned proof to the root (3
    # siblings), so verification climbs through 3 levels, computing (as Q) the
    # ancestor of leaf 1 at levels 1, 2, and 3 (root) -- none of which are
    # themselves siblings anyone sends.
    prior_sent: list[int] = []
    i1, leaf1_b64, siblings1_b64 = paytree.payment_proof_first_opt(1, prior_sent)
    await service.receive_payment(
        CHANNEL_ID,
        ReceivePaytreeFirstOptPaymentDTO(
            i=i1,
            leaf_b64=leaf1_b64,
            siblings_b64=siblings1_b64,
            paytree_max_i=MAX_STEPS,
        ),
    )
    prior_sent.append(1)

    q_keys_payment1 = [
        key_eytzinger(level, get_ancestor_at_level(1, level), DEPTH)
        for level in range(1, DEPTH + 1)
    ]
    expected_q_payment1 = {
        key_eytzinger(level, get_ancestor_at_level(1, level), DEPTH): bytes_to_b64(
            tree_levels[level][get_ancestor_at_level(1, level)]
        )
        for level in range(1, DEPTH + 1)
    }
    stored_q_payment1 = await node_repo.get_nodes(CHANNEL_ID, q_keys_payment1)
    assert stored_q_payment1 == expected_q_payment1

    # Payment 2: i=2, sequential, pruned proof (only 1 sibling -- the LCA
    # overlap with leaf 1 means the *received* sub-root is already known).
    i2, leaf2_b64, siblings2_b64 = paytree.payment_proof_first_opt(2, prior_sent)
    assert len(siblings2_b64) == 1
    await service.receive_payment(
        CHANNEL_ID,
        ReceivePaytreeFirstOptPaymentDTO(
            i=i2,
            leaf_b64=leaf2_b64,
            siblings_b64=siblings2_b64,
            paytree_max_i=MAX_STEPS,
        ),
    )
    prior_sent.append(2)

    q_keys_payment2 = [
        key_eytzinger(level, get_ancestor_at_level(2, level), DEPTH)
        for level in range(1, DEPTH + 1)
    ]
    expected_q_payment2 = {
        key_eytzinger(level, get_ancestor_at_level(2, level), DEPTH): bytes_to_b64(
            tree_levels[level][get_ancestor_at_level(2, level)]
        )
        for level in range(1, DEPTH + 1)
    }
    stored_q_payment2 = await node_repo.get_nodes(CHANNEL_ID, q_keys_payment2)
    assert stored_q_payment2 == expected_q_payment2

    # Payment 1's computed nodes are still there after payment 2 -- the
    # second payment's writes merged into the store, they didn't replace it.
    assert await node_repo.get_nodes(CHANNEL_ID, q_keys_payment1) == expected_q_payment1
