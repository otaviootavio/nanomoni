"""PayTree second optimization helpers (reuse P and computed Q nodes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .paytree import (
    Paytree,
    _cache_key,
    b64_to_bytes,
    compute_lcp,
    compute_tree_depth,
    verify_proof_to_known_node,
)


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
        sibling_position = (i >> level) ^ 1
        cached = node_cache_b64.get(_cache_key(level, sibling_position))
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
    """
    Verify second-optimization proof and return reconstructed siblings.
    """
    if i < 0 or i > max_i:
        return False, []

    depth = compute_tree_depth(max_i)
    send_levels = compute_send_levels(i=i, node_cache_b64=node_cache_b64, depth=depth)
    trusted_level = depth
    known_node_b64 = root_b64
    if last_verified_index is not None:
        k_max = compute_lcp(i, last_verified_index, depth)
        candidate_level = depth - k_max
        candidate_key = _cache_key(candidate_level, i >> candidate_level)
        candidate_node = node_cache_b64.get(candidate_key)
        if candidate_node is not None:
            trusted_level = candidate_level
            known_node_b64 = candidate_node

    # For early-stop verification we only need levels [0, trusted_level).
    # The client's pruned proof may include entries for higher levels too;
    # those are irrelevant once we verify against a trusted Q-node.
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
        known_node_hash = b64_to_bytes(known_node_b64)
        current = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in full_siblings_b64]
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
        i_val, leaf_b64, pruned, _ = self.payment_proof_with_full_siblings(
            i=i, node_cache_b64=node_cache_b64
        )
        return i_val, leaf_b64, pruned

    def payment_proof_with_full_siblings(
        self, *, i: int, node_cache_b64: Optional[dict[str, str]] = None
    ) -> tuple[int, str, list[str], list[str]]:
        """Generate pruned proof and also return full siblings for cache update."""
        cache = node_cache_b64 or {}
        _, leaf_b64, full_siblings = self.base.payment_proof(i=i)
        depth = compute_tree_depth(self.max_i)
        send_levels = compute_send_levels(i=i, node_cache_b64=cache, depth=depth)
        pruned = [full_siblings[level] for level in send_levels]
        return i, leaf_b64, pruned, full_siblings
