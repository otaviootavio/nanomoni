"""PayTree first optimization helpers (reuse known authentication siblings)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .paytree import (
    Paytree,
    _cache_key,
    b64_to_bytes,
    compute_lcp,
    compute_tree_depth,
    update_cache_with_siblings_and_path,
    verify_proof_to_known_node,
)


def compute_send_levels(
    *,
    i: int,
    last_verified_index: Optional[int],
    depth: int,
) -> list[int]:
    """Levels sent by first optimization: {0..depth-k_max-1}."""
    if i < 0:
        raise ValueError("i must be >= 0")
    if depth < 0:
        raise ValueError("depth must be >= 0")
    if last_verified_index is None:
        return list(range(depth))
    k_max = compute_lcp(i, last_verified_index, depth)
    return list(range(max(0, depth - k_max)))


def reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    node_cache_b64: dict[str, str],
) -> Optional[list[str]]:
    """Reconstruct full sibling list from pruned siblings + cache."""
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


def verify_pruned_paytree_proof(
    *,
    i: int,
    root_b64: str,
    leaf_b64: str,
    pruned_siblings_b64: list[str],
    max_i: int,
    last_verified_index: Optional[int],
    node_cache_b64: dict[str, str],
) -> tuple[bool, list[str], dict[str, str]]:
    """
    Verify first-optimization proof and return reconstructed siblings + updated cache.
    """
    if i < 0 or i > max_i:
        return False, [], node_cache_b64

    depth = compute_tree_depth(max_i)
    send_levels = compute_send_levels(
        i=i, last_verified_index=last_verified_index, depth=depth
    )
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
        leaf = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return False, [], node_cache_b64

    ok = False
    trusted_level: Optional[int] = None
    known_node_hash = None
    if last_verified_index is not None:
        k_max = compute_lcp(i, last_verified_index, depth)
        trusted_level = depth - k_max
        known_key = _cache_key(trusted_level, i >> trusted_level)
        known_node_b64 = node_cache_b64.get(known_key)
        if known_node_b64 is not None:
            try:
                known_node_hash = b64_to_bytes(known_node_b64)
            except Exception:
                known_node_hash = None

    if trusted_level is not None and known_node_hash is not None:
        ok = verify_proof_to_known_node(
            leaf_hash=leaf,
            leaf_index=i,
            siblings=siblings[:trusted_level],
            known_node_hash=known_node_hash,
            known_node_level=trusted_level,
        )
    else:
        try:
            root = b64_to_bytes(root_b64)
        except Exception:
            return False, [], node_cache_b64
        ok = verify_proof_to_known_node(
            leaf_hash=leaf,
            leaf_index=i,
            siblings=siblings,
            known_node_hash=root,
            known_node_level=depth,
        )
    if not ok:
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
class PaytreeFirstOpt:
    """Client helper for first-optimization pruned proofs."""

    base: Paytree

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "PaytreeFirstOpt":
        return PaytreeFirstOpt(base=Paytree.create(max_i=max_i, seed=seed))

    @property
    def max_i(self) -> int:
        return self.base.max_i

    @property
    def commitment_root_b64(self) -> str:
        return self.base.commitment_root_b64

    def payment_proof(
        self, *, i: int, last_verified_index: Optional[int] = None
    ) -> tuple[int, str, list[str]]:
        """Generate first-optimization proof with pruned sibling set."""
        _, leaf_b64, full_siblings = self.base.payment_proof(i=i)
        depth = compute_tree_depth(self.max_i)
        send_levels = compute_send_levels(
            i=i, last_verified_index=last_verified_index, depth=depth
        )
        pruned = [full_siblings[level] for level in send_levels]
        return i, leaf_b64, pruned
