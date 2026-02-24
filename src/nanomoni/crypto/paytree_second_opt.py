"""PayTree second optimization helpers (reuse P and computed Q nodes)."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Optional

from .merkle_index import (
    compute_lcp,
    compute_send_levels_second_opt,
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
    key,
)
from .merkle_tree import build_merkle_tree, hash_bytes, verify_proof_to_known_node


def _b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


def _bytes_to_b64(data: bytes) -> str:
    """Encode raw bytes into base64 string."""
    return base64.b64encode(data).decode("utf-8")


def _index_to_hash_from_tree(
    tree_levels: list[list[bytes]], level: int, position: int
) -> bytes:
    """Fetch hash at (level, position) from built tree; duplicate last node if out of range."""
    row = tree_levels[level]
    return row[min(position, len(row) - 1)]


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


def reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    node_cache_b64: dict[str, str],
    stop_level: Optional[int] = None,
) -> Optional[list[str]]:
    """Reconstruct complete sibling list from sparse levels + cache."""
    if len(pruned_siblings_b64) != len(send_levels):
        return None

    send_by_level = {level: sib for level, sib in zip(send_levels, pruned_siblings_b64)}
    full: list[str] = []
    target_depth = depth if stop_level is None else min(depth, max(0, stop_level))
    for level in range(target_depth):
        if level in send_by_level:
            full.append(send_by_level[level])
            continue
        pos = get_sibling_position_at_level(i, level)
        cached = node_cache_b64.get(key(level, pos))
        if cached is None:
            return None
        full.append(cached)
    return full


def verify_pruned_paytree_proof(
    *,
    i: int,
    root_b64: str,
    leaf_b64: str,
    pruned_siblings_b64: list[str],
    max_i: int,
    node_cache_b64: dict[str, str],
    last_verified_index: Optional[int] = None,
) -> tuple[bool, list[str]]:
    """Verify second-optimization proof and return reconstructed siblings."""
    if i < 0 or i > max_i:
        return False, []

    depth = compute_tree_depth(max_i)
    send_levels = compute_send_levels_second_opt(
        i=i, depth=depth, known_keys=set(node_cache_b64)
    )
    trusted_level = depth
    known_node_b64 = root_b64
    if last_verified_index is not None:
        k_max = compute_lcp(i, last_verified_index, depth)
        candidate_level = depth - k_max
        candidate_key = key(candidate_level, get_ancestor_at_level(i, candidate_level))
        candidate_node = node_cache_b64.get(candidate_key)
        if candidate_node is not None:
            trusted_level = candidate_level
            known_node_b64 = candidate_node

    send_levels_for_verification = [
        level for level in send_levels if level < trusted_level
    ]
    if len(pruned_siblings_b64) < len(send_levels_for_verification):
        return False, []
    pruned_for_verification = pruned_siblings_b64[: len(send_levels_for_verification)]

    full_siblings_b64 = reconstruct_full_siblings(
        i=i,
        depth=depth,
        pruned_siblings_b64=pruned_for_verification,
        send_levels=send_levels_for_verification,
        node_cache_b64=node_cache_b64,
        stop_level=trusted_level,
    )
    if full_siblings_b64 is None:
        return False, []

    try:
        known_node_hash = _b64_to_bytes(known_node_b64)
        current = _b64_to_bytes(leaf_b64)
        siblings = [_b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return False, []

    if not verify_proof_to_known_node(
        leaf_hash=current,
        leaf_index=i,
        siblings=siblings,
        known_node_hash=known_node_hash,
        known_node_level=trusted_level,
    ):
        return False, []

    return True, full_siblings_b64


@dataclass(frozen=True)
class PaytreeSecondOpt:
    """Client helper for second-optimization pruned proofs."""

    max_i: int
    commitment_root_b64: str
    _tree_levels: list[list[bytes]]

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "PaytreeSecondOpt":
        tree_levels, root_b64 = _create_tree(max_i=max_i, seed=seed)
        return PaytreeSecondOpt(
            max_i=max_i,
            commitment_root_b64=root_b64,
            _tree_levels=tree_levels,
        )

    def payment_proof(
        self, *, i: int, node_cache_b64: Optional[dict[str, str]] = None
    ) -> tuple[int, str, list[str]]:
        """Generate second-optimization proof with pruned sibling set."""
        i_val, leaf_b64, pruned, _ = self.payment_proof_with_full_siblings(
            i=i, node_cache_b64=node_cache_b64
        )
        return i_val, leaf_b64, pruned

    def payment_proof_with_full_siblings(
        self, *, i: int, node_cache_b64: Optional[dict[str, str]] = None
    ) -> tuple[int, str, list[str], list[str]]:
        """Generate pruned proof and also return full siblings for cache update."""
        cache = node_cache_b64 or {}
        leaf_hash, full_siblings = _get_merkle_proof(self._tree_levels, i)
        leaf_b64 = _bytes_to_b64(leaf_hash)
        full_siblings_b64 = [_bytes_to_b64(s) for s in full_siblings]
        depth = compute_tree_depth(self.max_i)
        send_levels = compute_send_levels_second_opt(
            i=i, depth=depth, known_keys=set(cache)
        )
        pruned = [full_siblings_b64[level] for level in send_levels]
        return i, leaf_b64, pruned, full_siblings_b64
