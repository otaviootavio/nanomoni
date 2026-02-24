"""In-memory verifier node storage for PayTree first-opt.

First-opt semantics: store only proof data (leaf + siblings from each verified proof).
The vendor retrieves missing nodes from these stored proofs to reconstruct the full
proof and validate. Storing computed path nodes belongs to paytree_second_opt.

Repositories own persistence. Keys: "level:position" (e.g. "0:3", "2:1").
"""

from __future__ import annotations

from typing import MutableMapping, Optional

from ...crypto.merkle_index import (
    compute_tree_depth,
    get_sibling_position_at_level,
    key,
)

VerifierRepoData = dict[str, str]
"""Verifier store data: key (level:position) -> base64 hash."""

VerifierRepoBytesData = dict[str, bytes]
"""Verifier store data (bytes): key (level:position) -> hash bytes."""


def store_root(repo: MutableMapping[str, str], root_b64: str, tree_size: int) -> None:
    """Store Merkle root in repo."""
    max_i = tree_size - 1
    depth = compute_tree_depth(max_i)
    repo[key(depth, 0)] = root_b64


def store_root_bytes(
    repo: MutableMapping[str, bytes], root: bytes, tree_size: int
) -> None:
    """Store Merkle root in repo (bytes variant)."""
    max_i = tree_size - 1
    depth = compute_tree_depth(max_i)
    repo[key(depth, 0)] = root


def store_proof(
    repo: MutableMapping[str, str],
    leaf_index: int,
    leaf_b64: str,
    siblings_b64: list[str],
) -> None:
    """Store leaf and sibling hashes from a verified proof (base64 variant).

    First-opt: only proof data is stored. Missing nodes for later pruned proofs
    are retrieved from these stored proofs, not from computed path nodes.
    """
    repo[key(0, leaf_index)] = leaf_b64
    for level, sibling_b64 in enumerate(siblings_b64):
        sibling_pos = get_sibling_position_at_level(leaf_index, level)
        repo[key(level, sibling_pos)] = sibling_b64


def store_proof_bytes(
    repo: MutableMapping[str, bytes],
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
) -> None:
    """Store leaf and sibling hashes from a verified proof (bytes variant).

    First-opt: only proof data is stored. Missing nodes for later pruned proofs
    are retrieved from these stored proofs, not from computed path nodes.
    """
    repo[key(0, leaf_index)] = leaf_hash
    for level, sibling_bytes in enumerate(siblings):
        sibling_pos = get_sibling_position_at_level(leaf_index, level)
        repo[key(level, sibling_pos)] = sibling_bytes


def get_node(
    repo: MutableMapping[str, str], level: int, position: int
) -> Optional[str]:
    """Get node hash (base64) by level and position. Returns None if not found."""
    return repo.get(key(level, position))


def get_node_bytes(
    repo: MutableMapping[str, bytes], level: int, position: int
) -> Optional[bytes]:
    """Get node hash (bytes) by level and position. Returns None if not found."""
    return repo.get(key(level, position))


# ---------------------------------------------------------------------------
# Repository classes (own persistence, dict-like)
# ---------------------------------------------------------------------------


class VerifierRepoBytes(dict[str, bytes]):
    """Verifier repo (bytes): stores root + proof data (leaf + siblings) only. No verification logic.

    First-opt: no computed path nodes. Composed flow: get_node from repo (from previous
    proofs) -> verify -> store_proof(leaf + siblings).
    """

    def store_root(self, root: bytes, tree_size: int) -> None:
        """Store Merkle root in repo."""
        store_root_bytes(self, root, tree_size)

    def store_proof(
        self, leaf_index: int, leaf_hash: bytes, siblings: list[bytes]
    ) -> None:
        """Store leaf and siblings from proof only (no path nodes). No verification."""
        store_proof_bytes(
            self, leaf_index=leaf_index, leaf_hash=leaf_hash, siblings=siblings
        )

    def get_node(self, level: int, position: int) -> bytes | None:
        """Get node hash by level and position. Returns None if not found."""
        return get_node_bytes(self, level, position)


class VerifierRepo:
    """Verifier repo (base64). Stores root + proof data (leaf + siblings) only. First-opt semantics."""

    def __init__(self, data: VerifierRepoData) -> None:
        self._data = data

    def save_root_b64(self, root_b64: str, tree_size: int) -> None:
        """Store root (base64) in repo."""
        store_root(self._data, root_b64, tree_size)

    def save_leaf_subproof_b64(
        self, leaf_index: int, leaf_b64: str, siblings_b64: list[str]
    ) -> None:
        """Verify leaf sub-proof (crypto) then store if valid. Raises on failure."""
        from .verifier import verifier_receive_leaf_subproof_b64

        verifier_receive_leaf_subproof_b64(
            self._data,
            leaf_index=leaf_index,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )

    @property
    def data(self) -> VerifierRepoData:
        """Underlying dict for persistence."""
        return self._data
