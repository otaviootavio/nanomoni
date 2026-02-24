"""Verifier logic for PayTree first-opt protocol.

Verifier is stateless: does crypto validation and index operations only.
Receives all parameters needed. No internal repository.
Composed flow: x = verifier.get_sub_root_position(...); y = repo.get_node(...);
              verifier.verify_leaf_subproof(...); repo.store_proof(...)
"""

from __future__ import annotations

import base64
from typing import Optional

from ...crypto.merkle_index import (
    compute_lcp,
    compute_send_levels_first_opt,
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
)
from ...crypto.merkle_tree import verify_proof_to_known_node
from .exceptions import NoSubTreeForSubPathError
from .verifier_store import (
    VerifierRepoData,
    get_node as verifier_store_get_node,
    get_node_bytes as verifier_store_get_node_bytes,
    store_proof,
    store_proof_bytes,
    store_root,
    store_root_bytes,
)


def _b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


# ---------------------------------------------------------------------------
# Verifier (stateless: crypto + index operations)
# ---------------------------------------------------------------------------


class Verifier:
    """Stateless verifier: crypto validation and index operations. Receives all params."""

    @staticmethod
    def get_sub_root_position(leaf_index: int, known_node_level: int) -> int:
        """Index op: position of sub-root (known node) at given level for leaf_index."""
        return get_ancestor_at_level(leaf_index, known_node_level)

    @staticmethod
    def verify_leaf_subproof(
        leaf_index: int,
        leaf_hash: bytes,
        siblings: list[bytes],
        known_node_hash: bytes,
        known_node_level: int,
    ) -> bool:
        """Verify leaf sub-proof against known node. Pure crypto, no persistence."""
        return verify_proof_to_known_node(
            leaf_hash=leaf_hash,
            leaf_index=leaf_index,
            siblings=siblings,
            known_node_hash=known_node_hash,
            known_node_level=known_node_level,
        )


def verifier_verify_leaf_subproof(
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
    known_node_hash: bytes,
    known_node_level: int,
) -> bool:
    """Verify leaf sub-proof against known node. Delegates to Verifier.verify_leaf_subproof."""
    return Verifier.verify_leaf_subproof(
        leaf_index=leaf_index,
        leaf_hash=leaf_hash,
        siblings=siblings,
        known_node_hash=known_node_hash,
        known_node_level=known_node_level,
    )


# ---------------------------------------------------------------------------
# Persistence (repo only) - delegate to verifier_store
# ---------------------------------------------------------------------------


def verifier_store_root(repo: dict[str, bytes], root: bytes, tree_size: int) -> None:
    """Store root in repo. Persistence only."""
    store_root_bytes(repo, root, tree_size)


# ---------------------------------------------------------------------------
# Composed flow: get -> verify -> conditionally store
# ---------------------------------------------------------------------------


def verifier_receive_root(repo: dict[str, bytes], root: bytes, tree_size: int) -> None:
    """Composed: store root in repo (persistence only for root)."""
    verifier_store_root(repo, root, tree_size)


def verifier_receive_leaf_subproof(
    repo: dict[str, bytes],
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
) -> None:
    """Composed: get known node from repo, verify (crypto), then store if valid."""
    known_node_level = len(siblings)
    sub_root_position = get_ancestor_at_level(leaf_index, known_node_level)
    sub_root_hash = verifier_store_get_node_bytes(
        repo, known_node_level, sub_root_position
    )
    if sub_root_hash is None:
        raise NoSubTreeForSubPathError("no sub tree for that sub path")

    if not verifier_verify_leaf_subproof(
        leaf_index=leaf_index,
        leaf_hash=leaf_hash,
        siblings=siblings,
        known_node_hash=sub_root_hash,
        known_node_level=known_node_level,
    ):
        raise ValueError("proof verification failed")

    store_proof_bytes(
        repo=repo,
        leaf_index=leaf_index,
        leaf_hash=leaf_hash,
        siblings=siblings,
    )


def verifier_receive_root_b64(
    repo: VerifierRepoData, root_b64: str, tree_size: int
) -> None:
    """Verifier receives root (base64) and tree size; stores root in repo."""
    store_root(repo, root_b64, tree_size)


def verifier_receive_leaf_subproof_b64(
    repo: VerifierRepoData,
    leaf_index: int,
    leaf_b64: str,
    siblings_b64: list[str],
) -> None:
    """Composed: get from repo, verify (crypto), then store if valid (base64 variant)."""
    known_node_level = len(siblings_b64)
    sub_root_position = get_ancestor_at_level(leaf_index, known_node_level)
    sub_root_b64 = verifier_store_get_node(repo, known_node_level, sub_root_position)
    if sub_root_b64 is None:
        raise NoSubTreeForSubPathError("no sub tree for that sub path")

    try:
        leaf_hash = _b64_to_bytes(leaf_b64)
        siblings = [_b64_to_bytes(s) for s in siblings_b64]
        sub_root_hash = _b64_to_bytes(sub_root_b64)
    except Exception:
        raise ValueError("invalid base64 in proof or repo")

    if not verifier_verify_leaf_subproof(
        leaf_index=leaf_index,
        leaf_hash=leaf_hash,
        siblings=siblings,
        known_node_hash=sub_root_hash,
        known_node_level=known_node_level,
    ):
        raise ValueError("proof verification failed")

    store_proof(
        repo=repo,
        leaf_index=leaf_index,
        leaf_b64=leaf_b64,
        siblings_b64=siblings_b64,
    )


def _reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    repo: VerifierRepoData,
    stop_level: Optional[int] = None,
) -> Optional[list[str]]:
    """Reconstruct sibling list from pruned siblings + repo."""
    if len(pruned_siblings_b64) != len(send_levels):
        return None

    target_depth = min(depth, stop_level) if stop_level is not None else depth
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
    """Verify first-optimization pruned proof and update repo with P(x) only."""
    if i < 0 or i > max_i:
        return False, [], repo

    depth = compute_tree_depth(max_i)
    send_levels = compute_send_levels_first_opt(
        i=i, last_verified_index=last_verified_index, depth=depth
    )

    trusted_level: Optional[int] = None
    known_node_hash = None
    if last_verified_index is not None:
        k_max = compute_lcp(i, last_verified_index, depth)
        trusted_level = depth - k_max
        known_node_b64 = verifier_store_get_node(
            repo, trusted_level, i >> trusted_level
        )
        if known_node_b64 is not None:
            try:
                known_node_hash = _b64_to_bytes(known_node_b64)
            except Exception:
                known_node_hash = None

    stop_level = (
        trusted_level
        if (trusted_level is not None and known_node_hash is not None)
        else None
    )
    send_levels_truncated = [
        lvl for lvl in send_levels if stop_level is None or lvl < stop_level
    ]
    full_siblings_b64 = _reconstruct_full_siblings(
        i=i,
        depth=depth,
        pruned_siblings_b64=pruned_siblings_b64[: len(send_levels_truncated)],
        send_levels=send_levels_truncated,
        repo=repo,
        stop_level=stop_level,
    )
    if full_siblings_b64 is None:
        return False, [], repo

    try:
        leaf = _b64_to_bytes(leaf_b64)
        siblings = [_b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return False, [], repo

    ok = False
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
            root = _b64_to_bytes(root_b64)
        except Exception:
            return False, [], repo
        ok = verify_proof_to_known_node(
            leaf_hash=leaf,
            leaf_index=i,
            siblings=siblings,
            known_node_hash=root,
            known_node_level=depth,
        )
    if not ok:
        return False, [], repo

    store_proof(
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
) -> tuple[bool, list[str], VerifierRepoData]:
    """Verify first-optimization proof and return reconstructed siblings + updated repo."""
    return verify_pruned_proof_and_update_repo_b64(
        i=i,
        root_b64=root_b64,
        leaf_b64=leaf_b64,
        pruned_siblings_b64=pruned_siblings_b64,
        max_i=max_i,
        last_verified_index=last_verified_index,
        repo=repo,
    )
