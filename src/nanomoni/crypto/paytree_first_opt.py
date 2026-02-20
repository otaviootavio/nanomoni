"""PayTree first optimization helpers (reuse known authentication siblings)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .paytree import (
    Paytree,
    _verify_merkle_proof,
    b64_to_bytes,
)


def _cache_key(level: int, position: int) -> str:
    return f"{level}:{position}"


def compute_tree_depth(max_i: int) -> int:
    """Return tree depth (number of sibling levels) for indices [0..max_i]."""
    if max_i < 0:
        raise ValueError("max_i must be >= 0")
    leaf_count = max_i + 1
    padded = 1 if leaf_count <= 1 else 1 << (leaf_count - 1).bit_length()
    return padded.bit_length() - 1


def compute_lcp(a: int, b: int, n: int) -> int:
    """Longest common prefix length for n-bit integers."""
    if a < 0 or b < 0:
        raise ValueError("indices must be >= 0")
    if n < 0:
        raise ValueError("n must be >= 0")
    xor = a ^ b
    if xor == 0:
        return n
    return max(0, n - xor.bit_length())


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


def update_cache_with_full_siblings(
    *,
    i: int,
    full_siblings_b64: list[str],
) -> dict[str, str]:
    """Store all known P(x) sibling nodes in the cache."""
    return {
        _cache_key(level, (i >> level) ^ 1): sibling_b64
        for level, sibling_b64 in enumerate(full_siblings_b64)
    }


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
        root = b64_to_bytes(root_b64)
    except Exception:
        return False, [], node_cache_b64

    ok = _verify_merkle_proof(leaf, siblings, root, i)
    if not ok:
        return False, [], node_cache_b64

    updated_cache = update_cache_with_full_siblings(
        i=i,
        full_siblings_b64=full_siblings_b64,
    )
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
