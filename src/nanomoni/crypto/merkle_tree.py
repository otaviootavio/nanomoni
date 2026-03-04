"""Merkle tree library: hashing, building trees, and verifying proofs.

Internal nodes: Hash(left, right). Verification recomputes root from leaf
upward using siblings; order (left, right) is determined by whether current
node is left or right child (even/odd index).

Use merkle_index for path/sibling indices and keys. Hash lookup (index_to_hash)
is provided by the caller: tree for issuer, cache for vendor.
"""

from __future__ import annotations

import hashlib

from nanomoni.crypto.merkle_index import (
    get_node_dependency_indexes,
    level_position_from_eytzinger,
)
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


def is_ancestor(
    level_a: int,
    pos_a: int,
    level_b: int,
    pos_b: int,
) -> bool:
    """True iff node A at (level_a, pos_a) is an ancestor of node B at (level_b, pos_b).

    Convention: level 0 = leaves, level depth = root. A is ancestor of B iff
    level_a > level_b and pos_a == (pos_b >> (level_a - level_b)).
    """
    if level_a <= level_b:
        return False
    return pos_a == (pos_b >> (level_a - level_b))


def build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
    level_b: int,
    pos_b: int,
    level_a: int,
    pos_a: int,
) -> list[tuple[int, int]]:
    """Return sibling indexes (level, position) from node B to ancestor A.

    Common case: B = leaf (level_b=0, pos_b=leaf_index), A = root (level_a=depth, pos_a=0).
    A node is treated as its own ancestor (returns []). Caller converts indexes to hashes.
    """
    if (level_a, pos_a) == (level_b, pos_b):
        return []
    if not is_ancestor(level_a, pos_a, level_b, pos_b):
        raise ValueError(
            f"A ({level_a},{pos_a}) is not an ancestor of B ({level_b},{pos_b})"
        )
    return [
        (level, (pos_b >> (level - level_b)) ^ 1) for level in range(level_b, level_a)
    ]


def verify_proof_of_leaf_a_given_ancestor_b(
    leaf_secret: bytes,
    leaf_index: int,
    merkle_proof: list[bytes],
    subroot_node: bytes,
    subroot_index: str,
    depth: int,
) -> None:
    """Verify that the leaf has a valid Merkle proof to the given sub-root.

    Generic pure verification: no store. Caller provides leaf (secret), leaf index,
    proof array, and the sub-root node (hash) with its Eytzinger index.
    When subroot equals the leaf itself (0, leaf_index), verifies hash(secret)==subroot_node.
    Raises ValueError if the sub-root is not on the leaf's path or proof fails.
    """
    ancestor_level, ancestor_position = level_position_from_eytzinger(
        int(subroot_index, 2), depth
    )
    if (ancestor_level, ancestor_position) != (0, leaf_index) and not is_ancestor(
        ancestor_level, ancestor_position, 0, leaf_index
    ):
        raise ValueError(
            f"Sub-root ({ancestor_level},{ancestor_position}) is not on path of leaf {leaf_index}"
        )
    leaf_hash = hash_bytes(leaf_secret)
    if not verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=merkle_proof,
        known_node_hash=subroot_node,
        known_node_level=ancestor_level,
    ):
        raise ValueError("proof verification failed")


def get_proof_dependency_indexes(
    sibling_indexes: list[tuple[int, int]], depth: int
) -> list[tuple[int, int]]:
    """Return union of dependency indexes for all sibling nodes in a proof.

    Single set of (level, pos) to batch-fetch for rebuilding the full proof.
    Works for both full proof (leaf -> root) and pruned proof (leaf -> sub-root).
    """
    seen: set[tuple[int, int]] = set()
    result: list[tuple[int, int]] = []
    for level, pos in sibling_indexes:
        for k in get_node_dependency_indexes(level, pos, depth):
            if k not in seen:
                seen.add(k)
                result.append(k)
    return result


def build_node_from_dependencies(
    level: int,
    position: int,
    node_hashes: dict[tuple[int, int], bytes],
    depth: int,
) -> bytes:
    """Compute hash at (level, position) from preloaded hashes (no store access).

    node_hashes is expected to be populated by a batch get of the indexes
    returned by get_proof_dependency_indexes (nodes and leaf hashes from secrets).
    """
    key = (level, position)
    if key in node_hashes:
        return node_hashes[key]
    if level == 0:
        raise KeyError(
            f"cannot rebuild node: leaf {position} not in batch result (missing from node/store or secrets)"
        )
    left = build_node_from_dependencies(level - 1, 2 * position, node_hashes, depth)
    right = build_node_from_dependencies(
        level - 1, 2 * position + 1, node_hashes, depth
    )
    return combine_children(left, right, True)
