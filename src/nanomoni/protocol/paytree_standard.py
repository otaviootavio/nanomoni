"""PayTree standard protocol: full proof (leaf -> root) per payment."""

from __future__ import annotations

from nanomoni.crypto.merkle_index import key_eytzinger, level_position_from_eytzinger
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    is_ancestor,
    verify_proof_of_leaf_a_given_ancestor_b,
    verify_proof_to_known_node,
)


def proof_indexes_standard(leaf_index: int, depth: int) -> list[tuple[int, int]]:
    """Return sibling indexes (level, position) for a full proof (leaf -> root).

    The upper level fetches secret and sibling hashes from storage using these
    indexes.
    """
    return build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, leaf_index, depth, 0
    )


def verify_proof(
    secret: bytes,
    leaf_index: int,
    siblings: list[bytes],
    subroot_node: bytes,
    subroot_index: str,
    depth: int,
) -> None:
    """Verify a Merkle proof against a sub-root (leaf preimage = secret).

    Raises ValueError if verification fails.
    """
    verify_proof_of_leaf_a_given_ancestor_b(
        secret, leaf_index, siblings, subroot_node, subroot_index, depth
    )


def verify_proof_with_leaf_hash(
    leaf_hash: bytes,
    leaf_index: int,
    siblings: list[bytes],
    subroot_node: bytes,
    subroot_index: str,
    depth: int,
) -> bool:
    """Verify a Merkle proof against a sub-root (leaf hash provided directly).

    Used when the upper layer has leaf_hash (e.g. from API payload) rather than
    the leaf preimage/secret. For standard proof to root: subroot = root at
    (depth, 0), subroot_index = key_eytzinger(depth, 0, depth).

    Returns True if valid, False otherwise.
    """
    ancestor_level, ancestor_position = level_position_from_eytzinger(
        int(subroot_index, 2), depth
    )
    if (ancestor_level, ancestor_position) != (0, leaf_index) and not is_ancestor(
        ancestor_level, ancestor_position, 0, leaf_index
    ):
        return False
    return verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=siblings,
        known_node_hash=subroot_node,
        known_node_level=ancestor_level,
    )


def subroot_index_standard(depth: int) -> str:
    """Return the Eytzinger key for the root (standard proof subroot)."""
    return key_eytzinger(depth, 0, depth)
