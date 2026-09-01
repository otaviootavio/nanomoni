"""Regression: rebuild_full_paytree_proof's dependency resolution is exactly
one repository read -- never a multi-round decomposition into children.

Prior behavior (before this fix) expanded an unresolved target down to its
two children and issued another get_nodes call, repeating up to `depth`
times. That traded a single unbounded-ish read for a bounded number of
reads, but still violated "one read at the start": a target the store
didn't hold at its own granularity, but could reconstruct from finer-grained
pieces, would trigger a second (or third...) round trip. This now fails the
rebuild instead of decomposing further -- exactly one get_nodes call, ever.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from typing import Optional

from nanomoni.application.shared.paytree_proof_rebuild import rebuild_full_paytree_proof
from nanomoni.crypto.merkle_index import get_sibling_position_at_level, key_eytzinger
from nanomoni.crypto.merkle_tree import build_merkle_tree, hash_bytes
from nanomoni.crypto.paytree import bytes_to_b64
from nanomoni.domain.shared.crypto_proof import CryptoProof
from nanomoni.domain.shared.proof_reference import PaymentScheme
from nanomoni.domain.vendor.entities import PaymentChannel, PaymentState

MAX_STEPS = 7  # 8 leaves -> depth 3
DEPTH = 3
CHANNEL_ID = "c1"


def _build_tree() -> tuple[bytes, list[list[bytes]]]:
    leaves = [hash_bytes(f"leaf{i}".encode()) for i in range(8)]
    return build_merkle_tree(leaves)


def _make_channel(commitment_b64: str) -> PaymentChannel:
    return PaymentChannel(
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


class _CountingNodeRepo:
    """Fake MerkleNodeRepository backed by a fixed dict; only get_nodes is
    exercised by rebuild_full_paytree_proof, so the rest are unused stubs."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.get_nodes_call_count = 0

    async def get_nodes(self, channel_id: str, keys: list[str]) -> dict[str, str]:
        self.get_nodes_call_count += 1
        return {k: self._values[k] for k in keys if k in self._values}

    async def get_channel_and_nodes(
        self, channel_id: str, read_keys: list[str]
    ) -> tuple[Optional[PaymentChannel], dict[str, str]]:
        raise NotImplementedError

    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None:
        raise NotImplementedError

    async def save_nodes_and_payment(
        self,
        channel_id: str,
        node_updates: dict[str, str],
        new_ref: int,
        channel: PaymentChannel,
        state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[int]]:
        raise NotImplementedError

    async def delete(self, channel_id: str) -> int:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_rebuild_succeeds_with_zero_repo_reads_when_extra_nodes_cover_everything() -> (
    None
):
    root, tree_levels = _build_tree()
    channel = _make_channel(bytes_to_b64(root))
    leaf_b64 = bytes_to_b64(tree_levels[0][0])

    extra_nodes_b64 = {
        key_eytzinger(
            level, get_sibling_position_at_level(0, level), DEPTH
        ): bytes_to_b64(tree_levels[level][get_sibling_position_at_level(0, level)])
        for level in range(DEPTH)
    }
    repo = _CountingNodeRepo({})

    result = await rebuild_full_paytree_proof(
        repo, CHANNEL_ID, channel, 0, leaf_b64, extra_nodes_b64=extra_nodes_b64
    )

    assert result is not None
    assert repo.get_nodes_call_count == 0


@pytest.mark.asyncio
async def test_rebuild_fails_instead_of_decomposing_a_target_into_its_children() -> (
    None
):
    """A target sibling not held at its own granularity must fail the rebuild,
    even when its two children ARE separately present in the store -- no
    second read is issued to try reconstructing it from them."""
    root, tree_levels = _build_tree()
    channel = _make_channel(bytes_to_b64(root))
    leaf_b64 = bytes_to_b64(tree_levels[0][0])

    # Full proof for leaf 0 needs siblings at (0,1), (1,1), (2,1). Store (0,1)
    # and (2,1) directly, but withhold (1,1) itself -- store only its two
    # children (0,2) and (0,3) instead, simulating data that could be
    # recombined but was never persisted as the node itself.
    level0_key = key_eytzinger(0, 1, DEPTH)
    level2_key = key_eytzinger(2, 1, DEPTH)
    child_a_key = key_eytzinger(0, 2, DEPTH)
    child_b_key = key_eytzinger(0, 3, DEPTH)
    repo = _CountingNodeRepo(
        {
            level0_key: bytes_to_b64(tree_levels[0][1]),
            level2_key: bytes_to_b64(tree_levels[2][1]),
            child_a_key: bytes_to_b64(tree_levels[0][2]),
            child_b_key: bytes_to_b64(tree_levels[0][3]),
        }
    )

    result = await rebuild_full_paytree_proof(repo, CHANNEL_ID, channel, 0, leaf_b64)

    assert result is None
    assert repo.get_nodes_call_count == 1
