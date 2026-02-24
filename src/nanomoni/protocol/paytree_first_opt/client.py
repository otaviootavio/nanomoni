"""Client helper for PayTree first-opt pruned proofs."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Optional

from ...crypto.merkle_index import (
    compute_send_levels_first_opt,
    compute_tree_depth,
    get_sibling_position_at_level,
)
from ...crypto.merkle_tree import build_merkle_tree, hash_bytes


def _bytes_to_b64(data: bytes) -> str:
    """Encode raw bytes into base64 string."""
    return base64.b64encode(data).decode("utf-8")


def _hash_at(tree_levels: list[list[bytes]], level: int, position: int) -> bytes:
    """Fetch hash at (level, position) from tree_levels; duplicate last node if out of range."""
    row = tree_levels[level]
    return row[min(position, len(row) - 1)]


def _create_tree(
    max_i: int, seed: Optional[bytes] = None
) -> tuple[list[list[bytes]], str]:
    """Build Merkle tree and return (tree_levels, commitment_root_b64)."""
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
    root_b64 = _bytes_to_b64(root)
    return tree_levels, root_b64


@dataclass(frozen=True)
class PaytreeFirstOpt:
    """Client helper for first-optimization pruned proofs."""

    max_i: int
    commitment_root_b64: str
    _tree_levels: list[list[bytes]]

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "PaytreeFirstOpt":
        tree_levels, root_b64 = _create_tree(max_i=max_i, seed=seed)
        return PaytreeFirstOpt(
            max_i=max_i,
            commitment_root_b64=root_b64,
            _tree_levels=tree_levels,
        )

    def payment_proof(
        self, *, i: int, last_verified_index: Optional[int] = None
    ) -> tuple[int, str, list[str]]:
        """Generate first-optimization proof with pruned sibling set."""
        if i < 0 or i > self.max_i:
            raise ValueError(f"Index i={i} out of range [0, {self.max_i}]")
        depth = compute_tree_depth(self.max_i)
        send_levels = compute_send_levels_first_opt(
            i=i, last_verified_index=last_verified_index, depth=depth
        )
        leaf_hash = _hash_at(self._tree_levels, 0, i)
        pruned_siblings = [
            _hash_at(self._tree_levels, level, get_sibling_position_at_level(i, level))
            for level in send_levels
        ]
        leaf_b64 = _bytes_to_b64(leaf_hash)
        pruned_b64 = [_bytes_to_b64(s) for s in pruned_siblings]
        return i, leaf_b64, pruned_b64
