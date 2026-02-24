"""Merkle tree library: hashing, building trees, and verifying proofs.

Internal nodes: Hash(left, right). Verification recomputes root from leaf
upward using siblings; order (left, right) is determined by whether current
node is left or right child (even/odd index).

Use merkle_index for path/sibling indices and keys. Hash lookup (index_to_hash)
is provided by the caller: tree for issuer, cache for vendor.
"""

from __future__ import annotations

import hashlib
from typing import Final

SHA256: Final[str] = "sha256"


def hash_bytes(data: bytes) -> bytes:
    """Hash bytes using SHA-256."""
    return hashlib.new(SHA256, data).digest()


def combine_children(left: bytes, right: bytes, left_is_first: bool) -> bytes:
    """Parent hash from children: Hash(left, right) or Hash(right, left).

    left_is_first = current is left child; Hash(N'_q, N_p) when right sibling,
    Hash(N_p, N'_q) when left sibling.
    """
    if left_is_first:
        return hash_bytes(left + right)
    return hash_bytes(right + left)


def _next_power_of_two(n: int) -> int:
    """Smallest power of 2 >= n."""
    if n <= 0:
        return 1
    if n & (n - 1) == 0:
        return n
    return 1 << (n.bit_length())


def build_merkle_tree(leaves: list[bytes]) -> tuple[bytes, list[list[bytes]]]:
    """Build a binary Merkle tree from leaf hashes.

    Internal nodes: Hash(N_left, N_right). Pads to next power of two by
    duplicating last leaf.

    Returns:
        (root_hash, tree_levels) where tree_levels[level][position] is the hash
        at that (level, position). Level 0 = leaves, last level = root.
    """
    if not leaves:
        raise ValueError("Cannot build Merkle tree with empty leaves")

    padded_size = _next_power_of_two(len(leaves))
    padded_leaves = leaves + [leaves[-1]] * (padded_size - len(leaves))
    tree_levels: list[list[bytes]] = [padded_leaves]
    current_level = padded_leaves

    while len(current_level) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = (
                current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
            )
            parent = hash_bytes(left + right)
            next_level.append(parent)
        tree_levels.append(next_level)
        current_level = next_level

    root = tree_levels[-1][0]
    return root, tree_levels


def verify_proof_to_known_node(
    *,
    leaf_hash: bytes,
    leaf_index: int,
    siblings: list[bytes],
    known_node_hash: bytes,
    known_node_level: int,
) -> bool:
    """Verify a Merkle proof segment from leaf up to a known node.

    Start with leaf hash; for each level, combine with sibling using left/right
    order. Success iff recomputed root matches known_node_hash.

    siblings: one hash per level 0..known_node_level-1 (authentication path).
    """
    if leaf_index < 0 or known_node_level < 0:
        return False
    if len(siblings) != known_node_level:
        return False

    current = leaf_hash
    current_index = leaf_index
    for sibling in siblings:
        left_is_first = (current_index % 2) == 0
        current = combine_children(current, sibling, left_is_first)
        current_index = current_index // 2
    return current == known_node_hash
