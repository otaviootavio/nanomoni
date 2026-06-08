"""PayTree: Merkle tree-based cumulative micropayment proofs.

Composes merkle_index (path/siblings by index) and merkle_tree (hashing,
build, verify). Hash lookup (index_to_hash) is from the built tree for
the issuer and from the cache for the vendor.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Optional

from .merkle_index import (
    get_sibling_position_at_level,
    is_left_child,
    key,
    parent_position,
)
from .merkle_tree import (
    build_merkle_tree,
    hash_bytes,
    verify_proof_to_known_node,
)
from nanomoni.protocol import proof_indexes_first_opt


def b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


def bytes_to_b64(data: bytes) -> str:
    """Encode raw bytes into base64 string."""
    return base64.b64encode(data).decode("utf-8")


def _index_to_hash_from_tree(
    tree_levels: list[list[bytes]], level: int, position: int
) -> bytes:
    """Fetch hash at (level, position) from built tree; duplicate last node if out of range."""
    row = tree_levels[level]
    return row[min(position, len(row) - 1)]


def update_cache_with_siblings_and_path(
    *,
    i: int,
    leaf_b64: str,
    full_siblings_b64: list[str],
    node_cache_b64: dict[str, str],
) -> Optional[dict[str, str]]:
    """Store both P(x) siblings and Q(x) computed path nodes.

    Mutates *node_cache_b64* in place and returns it (or ``None`` on
    decode error).
    """
    try:
        current = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return None

    node_cache_b64[key(0, i)] = leaf_b64
    current_position = i

    for level, sibling_bytes in enumerate(siblings):
        sibling_pos = get_sibling_position_at_level(i, level)
        node_cache_b64[key(level, sibling_pos)] = bytes_to_b64(sibling_bytes)
        parent = hash_bytes(
            current + sibling_bytes
            if is_left_child(current_position)
            else sibling_bytes + current
        )
        current = parent
        current_position = parent_position(current_position)
        node_cache_b64[key(level + 1, current_position)] = bytes_to_b64(current)

    return node_cache_b64


def _get_merkle_proof(
    tree_levels: list[list[bytes]], leaf_index: int
) -> tuple[bytes, list[bytes]]:
    """Merkle proof (leaf hash + sibling hashes) for leaf_index using index_to_hash from tree."""
    if not tree_levels:
        raise ValueError("Empty tree levels")
    depth = len(tree_levels) - 1
    if leaf_index < 0 or leaf_index >= len(tree_levels[0]):
        raise ValueError(
            f"Leaf index {leaf_index} out of range [0, {len(tree_levels[0])})"
        )

    leaf_hash = tree_levels[0][leaf_index]
    siblings: list[bytes] = []
    for level in range(depth):
        pos = get_sibling_position_at_level(leaf_index, level)
        siblings.append(_index_to_hash_from_tree(tree_levels, level, pos))
    return leaf_hash, siblings


def _get_merkle_proof_pruned(
    tree_levels: list[list[bytes]],
    leaf_index: int,
    prior_leaves: list[int],
) -> tuple[bytes, list[bytes]]:
    """Pruned Merkle proof (leaf -> sub-root) using LCA with prior leaves.

    Returns (leaf_hash, siblings) where siblings are only up to the sub-root
    determined by proof_indexes_first_opt.
    """
    if not tree_levels:
        raise ValueError("Empty tree levels")
    depth = len(tree_levels) - 1
    if leaf_index < 0 or leaf_index >= len(tree_levels[0]):
        raise ValueError(
            f"Leaf index {leaf_index} out of range [0, {len(tree_levels[0])})"
        )

    pruned_indexes = proof_indexes_first_opt(leaf_index, prior_leaves, depth)
    leaf_hash = tree_levels[0][leaf_index]
    siblings = [
        _index_to_hash_from_tree(tree_levels, level, position)
        for level, position in pruned_indexes
    ]
    return leaf_hash, siblings


def _verify_merkle_proof(
    leaf_hash: bytes, siblings: list[bytes], root: bytes, leaf_index: int
) -> bool:
    """Verify a Merkle proof against a root."""
    return verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=siblings,
        known_node_hash=root,
        known_node_level=len(siblings),
    )


@dataclass(frozen=True)
class Paytree:
    """
    Client-side PayTree helper (issuer).

    Builds the Merkle tree and generates per-payment proofs (i, leaf_b64, siblings_b64[])
    using index_to_hash from the built tree.
    """

    max_i: int
    commitment_root_b64: str
    _tree_levels: list[list[bytes]]
    _leaf_secrets: list[bytes]

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "Paytree":
        """Create a PayTree with max_i + 1 leaves (indices 0 to max_i)."""
        if max_i < 0:
            raise ValueError("max_i must be >= 0")

        if seed is not None:
            leaf_secrets: list[bytes] = []
            for i in range(max_i + 1):
                h = hashlib.sha256()
                h.update(seed)
                h.update(i.to_bytes(8, "big"))
                leaf_secrets.append(h.digest())
        else:
            leaf_secrets = [os.urandom(32) for _ in range(max_i + 1)]

        leaves = [hash_bytes(secret) for secret in leaf_secrets]
        root, tree_levels = build_merkle_tree(leaves)
        root_b64 = bytes_to_b64(root)

        return Paytree(
            max_i=max_i,
            commitment_root_b64=root_b64,
            _tree_levels=tree_levels,
            _leaf_secrets=leaf_secrets,
        )

    def payment_proof(self, *, i: int) -> tuple[int, str, list[str]]:
        """Generate payment proof for index i: (i, leaf_b64, siblings_b64[])."""
        if i < 0 or i > self.max_i:
            raise ValueError(f"Index i={i} out of range [0, {self.max_i}]")

        leaf_hash, siblings = _get_merkle_proof(self._tree_levels, i)
        leaf_b64 = bytes_to_b64(leaf_hash)
        siblings_b64 = [bytes_to_b64(s) for s in siblings]
        return i, leaf_b64, siblings_b64

    def payment_proof_first_opt(
        self, i: int, prior_sent_indexes: list[int]
    ) -> tuple[int, str, list[str]]:
        """Generate pruned payment proof for index i (first-opt: leaf -> sub-root).

        prior_sent_indexes: leaf indexes already sent in this session (order matters).
        Returns (i, leaf_b64, siblings_b64[]) with fewer siblings when paths overlap.
        """
        if i < 0 or i > self.max_i:
            raise ValueError(f"Index i={i} out of range [0, {self.max_i}]")

        leaf_hash, siblings = _get_merkle_proof_pruned(
            self._tree_levels, i, prior_sent_indexes
        )
        leaf_b64 = bytes_to_b64(leaf_hash)
        siblings_b64 = [bytes_to_b64(s) for s in siblings]
        return i, leaf_b64, siblings_b64


def compute_cumulative_owed_amount(*, i: int, unit_value: int) -> int:
    """Compute owed amount from the PayTree index i and unit value."""
    if i < 0:
        raise ValueError("i must be >= 0")
    if unit_value <= 0:
        raise ValueError("unit_value must be > 0")
    return i * unit_value


def verify_paytree_proof(
    *,
    i: int,
    leaf_b64: str,
    siblings_b64: list[str],
    root_b64: str,
) -> bool:
    """Verify a PayTree proof against a commitment root."""
    try:
        leaf_hash = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in siblings_b64]
        root = b64_to_bytes(root_b64)
    except Exception:
        return False
    return _verify_merkle_proof(leaf_hash, siblings, root, i)
