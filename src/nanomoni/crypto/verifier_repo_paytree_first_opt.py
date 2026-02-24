"""In-memory repository for PayTree first-opt verifier node storage.

Single responsibility: store and retrieve Merkle tree nodes (root, leaf hashes,
sibling hashes) by level:position key. Used by the verifier to accumulate nodes
from verified proofs and reuse them when verifying pruned proofs.

Keys: "level:position" (e.g. "0:3", "2:1"). Values: base64-encoded hashes.
"""

from __future__ import annotations

from typing import Optional

from .merkle_index import compute_tree_depth, get_sibling_position_at_level, key


VerifierRepo = dict[str, str]
"""In-memory verifier repo: key (level:position) -> base64 hash."""

VerifierRepoBytes = dict[str, bytes]
"""Verifier repo with raw bytes values (for tests)."""


def store_root(repo: VerifierRepo, root_b64: str, tree_size: int) -> None:
    """Store Merkle root in repo."""
    max_i = tree_size - 1
    depth = compute_tree_depth(max_i)
    repo[key(depth, 0)] = root_b64


def store_root_bytes(repo: VerifierRepoBytes, root: bytes, tree_size: int) -> None:
    """Store Merkle root in repo (bytes variant)."""
    max_i = tree_size - 1
    depth = compute_tree_depth(max_i)
    repo[key(depth, 0)] = root


def store_proof(
    repo: VerifierRepo,
    leaf_index: int,
    leaf_b64: str,
    siblings_b64: list[str],
) -> None:
    """Store leaf and sibling hashes from a verified proof."""
    repo[key(0, leaf_index)] = leaf_b64
    for level, sibling_b64 in enumerate(siblings_b64):
        sibling_pos = get_sibling_position_at_level(leaf_index, level)
        repo[key(level, sibling_pos)] = sibling_b64


def store_proof_bytes(
    repo: VerifierRepoBytes,
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
) -> None:
    """Store leaf and sibling hashes from a verified proof (bytes variant)."""
    repo[key(0, leaf_index)] = leaf_hash
    for level, sibling_bytes in enumerate(siblings):
        sibling_pos = get_sibling_position_at_level(leaf_index, level)
        repo[key(level, sibling_pos)] = sibling_bytes


def get_node(repo: VerifierRepo, level: int, position: int) -> Optional[str]:
    """Get node hash (base64) by level and position. Returns None if not found."""
    return repo.get(key(level, position))


def get_node_bytes(
    repo: VerifierRepoBytes, level: int, position: int
) -> Optional[bytes]:
    """Get node hash (bytes) by level and position. Returns None if not found."""
    return repo.get(key(level, position))
