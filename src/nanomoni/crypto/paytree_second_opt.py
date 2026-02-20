"""PayTree second optimization helpers (reuse P and computed Q nodes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .paytree import (
    Paytree,
    b64_to_bytes,
    bytes_to_b64,
    hash_bytes,
)
from .paytree_first_opt import compute_tree_depth


def _cache_key(level: int, position: int) -> str:
    return f"{level}:{position}"


def compute_send_levels(
    *,
    i: int,
    node_cache_b64: dict[str, str],
    depth: int,
) -> list[int]:
    """Levels sent by second optimization."""
    if i < 0:
        raise ValueError("i must be >= 0")
    if depth < 0:
        raise ValueError("depth must be >= 0")
    return [
        level
        for level in range(depth)
        if _cache_key(level, (i >> level) ^ 1) not in node_cache_b64
    ]


def reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    node_cache_b64: dict[str, str],
) -> Optional[list[str]]:
    """Reconstruct complete sibling list from sparse levels + cache."""
    if len(pruned_siblings_b64) != len(send_levels):
        return None

    send_by_level = {level: sib for level, sib in zip(send_levels, pruned_siblings_b64)}
    full: list[str] = []
    for level in range(depth):
        if level in send_by_level:
            full.append(send_by_level[level])
            continue
        sibling_position = (i >> level) ^ 1
        cached = node_cache_b64.get(_cache_key(level, sibling_position))
        if cached is None:
            return None
        full.append(cached)
    return full


def update_cache_with_siblings_and_path(
    *,
    i: int,
    leaf_b64: str,
    full_siblings_b64: list[str],
    node_cache_b64: dict[str, str],
) -> Optional[dict[str, str]]:
    """Store both P(x) siblings and Q(x) computed path nodes."""
    try:
        current = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return None

    updated = dict(node_cache_b64)

    # Store Q(x) level 0 (leaf node)
    updated[_cache_key(0, i)] = leaf_b64

    current_position = i
    for level, sibling_bytes in enumerate(siblings):
        sibling_pos = current_position ^ 1
        updated[_cache_key(level, sibling_pos)] = bytes_to_b64(sibling_bytes)

        if (current_position % 2) == 0:
            parent = hash_bytes(current + sibling_bytes)
        else:
            parent = hash_bytes(sibling_bytes + current)

        current = parent
        current_position = current_position // 2
        updated[_cache_key(level + 1, current_position)] = bytes_to_b64(current)

    return updated


def verify_pruned_paytree_proof(
    *,
    i: int,
    root_b64: str,
    leaf_b64: str,
    pruned_siblings_b64: list[str],
    max_i: int,
    node_cache_b64: dict[str, str],
) -> tuple[bool, list[str], dict[str, str]]:
    """
    Verify second-optimization proof and return reconstructed siblings + updated cache.
    """
    if i < 0 or i > max_i:
        return False, [], node_cache_b64

    depth = compute_tree_depth(max_i)
    send_levels = compute_send_levels(i=i, node_cache_b64=node_cache_b64, depth=depth)
    full_siblings_b64 = reconstruct_full_siblings(
        i=i,
        depth=depth,
        pruned_siblings_b64=pruned_siblings_b64,
        send_levels=send_levels,
        node_cache_b64=node_cache_b64,
    )
    if full_siblings_b64 is None:
        return False, [], node_cache_b64

    try:
        root = b64_to_bytes(root_b64)
        current = b64_to_bytes(leaf_b64)
        current_position = i
        for sibling_b64 in full_siblings_b64:
            sibling = b64_to_bytes(sibling_b64)
            if (current_position % 2) == 0:
                current = hash_bytes(current + sibling)
            else:
                current = hash_bytes(sibling + current)
            current_position = current_position // 2
    except Exception:
        return False, [], node_cache_b64

    if current != root:
        return False, [], node_cache_b64

    updated_cache = update_cache_with_siblings_and_path(
        i=i,
        leaf_b64=leaf_b64,
        full_siblings_b64=full_siblings_b64,
        node_cache_b64=node_cache_b64,
    )
    if updated_cache is None:
        return False, [], node_cache_b64
    return True, full_siblings_b64, updated_cache


@dataclass(frozen=True)
class PaytreeSecondOpt:
    """Client helper for second-optimization pruned proofs."""

    base: Paytree

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "PaytreeSecondOpt":
        return PaytreeSecondOpt(base=Paytree.create(max_i=max_i, seed=seed))

    @property
    def max_i(self) -> int:
        return self.base.max_i

    @property
    def commitment_root_b64(self) -> str:
        return self.base.commitment_root_b64

    def payment_proof(
        self, *, i: int, node_cache_b64: Optional[dict[str, str]] = None
    ) -> tuple[int, str, list[str]]:
        """Generate second-optimization proof with pruned sibling set."""
        cache = node_cache_b64 or {}
        _, leaf_b64, full_siblings = self.base.payment_proof(i=i)
        depth = compute_tree_depth(self.max_i)
        send_levels = compute_send_levels(i=i, node_cache_b64=cache, depth=depth)
        pruned = [full_siblings[level] for level in send_levels]
        return i, leaf_b64, pruned
