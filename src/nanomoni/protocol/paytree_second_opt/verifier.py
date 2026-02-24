"""Verifier for PayTree second-opt: pruned proof → reconstruct from repo (P ∪ Q) → verify → store P + Q."""

from __future__ import annotations

import base64
from typing import Optional

from ...crypto.merkle_index import (
    compute_lcp,
    compute_send_levels_second_opt,
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
    key,
)
from ...crypto.merkle_tree import verify_proof_to_known_node
from .verifier_store import (
    VerifierRepoData,
    get_node as verifier_store_get_node,
    store_proof_with_path,
)


def _b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


def _reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    repo: VerifierRepoData,
    stop_level: Optional[int] = None,
) -> Optional[list[str]]:
    """Reconstruct full sibling list from pruned siblings + repo (P ∪ Q)."""
    if len(pruned_siblings_b64) != len(send_levels):
        return None
    target_depth = depth if stop_level is None else min(depth, max(0, stop_level))
    send_by_level = {level: sib for level, sib in zip(send_levels, pruned_siblings_b64)}
    full: list[str] = []
    for level in range(target_depth):
        if level in send_by_level:
            full.append(send_by_level[level])
            continue
        pos = get_sibling_position_at_level(i, level)
        node_b64 = verifier_store_get_node(repo, level, pos)
        if node_b64 is None:
            return None
        full.append(node_b64)
    return full


def verify_pruned_proof_and_update_repo_b64(
    *,
    i: int,
    root_b64: str,
    leaf_b64: str,
    pruned_siblings_b64: list[str],
    max_i: int,
    last_verified_index: Optional[int],
    repo: VerifierRepoData,
) -> tuple[bool, list[str], VerifierRepoData]:
    """Verify second-opt pruned proof and update repo with P(x) + Q(x).

    Reconstructs full siblings from repo (proof data and computed path from previous
    proofs), verifies to root or to known sub-root from repo, then stores proof + path.
    """
    if i < 0 or i > max_i:
        return False, [], repo

    depth = compute_tree_depth(max_i)
    known_keys = set(repo)
    send_levels = compute_send_levels_second_opt(
        i=i, depth=depth, known_keys=known_keys
    )

    trusted_level = depth
    known_node_b64 = root_b64
    if last_verified_index is not None:
        k_max = compute_lcp(i, last_verified_index, depth)
        candidate_level = depth - k_max
        candidate_pos = get_ancestor_at_level(i, candidate_level)
        candidate_key = key(candidate_level, candidate_pos)
        candidate_node = repo.get(candidate_key)
        if candidate_node is not None:
            trusted_level = candidate_level
            known_node_b64 = candidate_node

    send_levels_for_verification = [
        level for level in send_levels if level < trusted_level
    ]
    if len(pruned_siblings_b64) < len(send_levels_for_verification):
        return False, [], repo
    pruned_for_verification = pruned_siblings_b64[: len(send_levels_for_verification)]

    full_siblings_b64 = _reconstruct_full_siblings(
        i=i,
        depth=depth,
        pruned_siblings_b64=pruned_for_verification,
        send_levels=send_levels_for_verification,
        repo=repo,
        stop_level=trusted_level,
    )
    if full_siblings_b64 is None:
        return False, [], repo

    try:
        leaf = _b64_to_bytes(leaf_b64)
        siblings = [_b64_to_bytes(s) for s in full_siblings_b64]
        known_node_hash = _b64_to_bytes(known_node_b64)
    except Exception:
        return False, [], repo

    if not verify_proof_to_known_node(
        leaf_hash=leaf,
        leaf_index=i,
        siblings=siblings,
        known_node_hash=known_node_hash,
        known_node_level=trusted_level,
    ):
        return False, [], repo

    store_proof_with_path(
        repo=repo,
        leaf_index=i,
        leaf_b64=leaf_b64,
        siblings_b64=full_siblings_b64,
    )
    return True, full_siblings_b64, repo


def verify_pruned_paytree_proof(
    *,
    i: int,
    root_b64: str,
    leaf_b64: str,
    pruned_siblings_b64: list[str],
    max_i: int,
    last_verified_index: Optional[int],
    repo: VerifierRepoData,
) -> tuple[bool, list[str]]:
    """Verify second-opt pruned proof, update repo in place with P+Q, return full siblings."""
    ok, full_siblings_b64, _ = verify_pruned_proof_and_update_repo_b64(
        i=i,
        root_b64=root_b64,
        leaf_b64=leaf_b64,
        pruned_siblings_b64=pruned_siblings_b64,
        max_i=max_i,
        last_verified_index=last_verified_index,
        repo=repo,
    )
    return ok, full_siblings_b64
