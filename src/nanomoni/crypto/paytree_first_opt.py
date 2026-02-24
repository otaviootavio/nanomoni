"""PayTree first optimization helpers (reuse known authentication siblings).

Includes prover-side and verifier-side functions: build tree, send root,
send leaf sub-proof with first optimization (pruned siblings based on LCP
with prior verified leaves), and verifier-side verification.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Iterable, Optional

from .merkle_index import (
    compute_lcp,
    compute_send_levels_first_opt,
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
)
from .merkle_tree import build_merkle_tree, hash_bytes, verify_proof_to_known_node
from .prover_repo_paytree_first_opt import (
    ProverRepo,
    get_node as prover_repo_get_node,
    store_tree as prover_repo_store_tree,
)
from .verifier_repo_paytree_first_opt import (
    VerifierRepo,
    VerifierRepoBytes,
    get_node as verifier_repo_get_node,
    get_node_bytes as verifier_repo_get_node_bytes,
    store_proof as verifier_repo_store_proof,
    store_proof_bytes as verifier_repo_store_proof_bytes,
    store_root as verifier_repo_store_root,
    store_root_bytes as verifier_repo_store_root_bytes,
)


def _b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


def _bytes_to_b64(data: bytes) -> str:
    """Encode raw bytes into base64 string."""
    return base64.b64encode(data).decode("utf-8")


def _hash_at(tree_levels: list[list[bytes]], level: int, position: int) -> bytes:
    """Fetch hash at (level, position) from tree_levels; duplicate last node if out of range."""
    row = tree_levels[level]
    return row[min(position, len(row) - 1)]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NoSubTreeForSubPathError(Exception):
    """Raised when the verifier has no sub-root in repo for the given sub-proof."""

    pass


# ---------------------------------------------------------------------------
# Prover (low-level API for tree from arbitrary leaves)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProverState:
    """Prover state: built tree and metadata."""

    root: bytes
    repo: ProverRepo
    tree_size: int  # number of leaves (max_i + 1)
    depth: int


def prover_build_tree(leaves: list[bytes]) -> ProverState:
    """Prover generates Merkle tree from leaves."""
    if not leaves:
        raise ValueError("Cannot build Merkle tree with empty leaves")
    root, tree_levels = build_merkle_tree(leaves)
    tree_size = len(tree_levels[0])
    depth = len(tree_levels) - 1
    repo: ProverRepo = {}
    prover_repo_store_tree(repo, tree_levels)
    return ProverState(root=root, repo=repo, tree_size=tree_size, depth=depth)


def prover_send_root(state: ProverState) -> tuple[bytes, int]:
    """Prover sends Merkle root and tree size to verifier."""
    return state.root, state.tree_size


def prover_send_leaf_subproof_firstopt(
    state: ProverState,
    leaf_index: int,
    already_sent_indexes: Optional[Iterable[int]] = None,
) -> tuple[int, int, bytes, list[bytes]]:
    """Prover sends leaf X (index, tree size) and its pruned sub-proof using first optimization.

    First optimization (from the paper): omit sibling hashes at levels above
    n - k_max - 1, where k_max = max LCP(leaf_index, a) over all prior leaves a
    in already_sent_indexes. Prior proofs already verified nodes on the path
    from those leaves to the root; the pruned path P_pruned(x) sends only
    levels j in {0, .., n - k_max - 1}. When already_sent_indexes is None or
    empty, send the full authentication path.

    Returns:
        (leaf_index, tree_size, leaf_hash, siblings)
        siblings are only for levels in send_levels (pruned per first opt).
    """
    if leaf_index < 0 or leaf_index >= state.tree_size:
        raise ValueError(f"Leaf index {leaf_index} out of range [0, {state.tree_size})")
    depth = state.depth
    if already_sent_indexes is None:
        send_levels = list(range(depth))
    else:
        indexes = list(already_sent_indexes)
        if not indexes:
            send_levels = list(range(depth))
        else:
            k_max = max(compute_lcp(leaf_index, a, depth) for a in indexes)
            send_levels = list(range(max(0, depth - k_max)))
    leaf_hash = prover_repo_get_node(state.repo, 0, leaf_index)
    if leaf_hash is None:
        raise ValueError(f"Leaf index {leaf_index} not in prover repo")
    siblings = []
    for level in send_levels:
        pos = get_sibling_position_at_level(leaf_index, level)
        sib = prover_repo_get_node(state.repo, level, pos)
        if sib is None:
            raise ValueError(
                f"Sibling at level {level} position {pos} not in prover repo"
            )
        siblings.append(sib)
    return leaf_index, state.tree_size, leaf_hash, siblings


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


def verifier_receive_root(repo: VerifierRepoBytes, root: bytes, tree_size: int) -> None:
    """Verifier receives root and tree size; stores root in repo."""
    verifier_repo_store_root_bytes(repo, root, tree_size)


def verifier_receive_leaf_subproof(
    repo: VerifierRepoBytes,
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
) -> None:
    """Verifier receives leaf sub-proof; looks up sub-root, verifies, then updates repo."""
    known_node_level = len(siblings)
    sub_root_position = get_ancestor_at_level(leaf_index, known_node_level)
    sub_root_hash = verifier_repo_get_node_bytes(
        repo, known_node_level, sub_root_position
    )
    if sub_root_hash is None:
        raise NoSubTreeForSubPathError("no sub tree for that sub path")

    ok = verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=siblings,
        known_node_hash=sub_root_hash,
        known_node_level=known_node_level,
    )
    if not ok:
        raise ValueError("proof verification failed")

    verifier_repo_store_proof_bytes(
        repo=repo,
        leaf_index=leaf_index,
        leaf_hash=leaf_hash,
        siblings=siblings,
    )


def verifier_receive_root_b64(
    repo: VerifierRepo, root_b64: str, tree_size: int
) -> None:
    """Verifier receives root (base64) and tree size; stores root in repo."""
    verifier_repo_store_root(repo, root_b64, tree_size)


def verifier_receive_leaf_subproof_b64(
    repo: VerifierRepo,
    leaf_index: int,
    leaf_b64: str,
    siblings_b64: list[str],
) -> None:
    """Verifier receives leaf sub-proof (base64); looks up sub-root, verifies, updates repo."""
    known_node_level = len(siblings_b64)
    sub_root_position = get_ancestor_at_level(leaf_index, known_node_level)
    sub_root_b64 = verifier_repo_get_node(repo, known_node_level, sub_root_position)
    if sub_root_b64 is None:
        raise NoSubTreeForSubPathError("no sub tree for that sub path")

    try:
        leaf_hash = _b64_to_bytes(leaf_b64)
        siblings = [_b64_to_bytes(s) for s in siblings_b64]
        sub_root_hash = _b64_to_bytes(sub_root_b64)
    except Exception:
        raise ValueError("invalid base64 in proof or repo")

    ok = verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=siblings,
        known_node_hash=sub_root_hash,
        known_node_level=known_node_level,
    )
    if not ok:
        raise ValueError("proof verification failed")

    verifier_repo_store_proof(
        repo=repo,
        leaf_index=leaf_index,
        leaf_b64=leaf_b64,
        siblings_b64=siblings_b64,
    )


# ---------------------------------------------------------------------------
# Pruned proof support (reconstruct from repo, early-stop verification)
# ---------------------------------------------------------------------------


def _reconstruct_full_siblings(
    *,
    i: int,
    depth: int,
    pruned_siblings_b64: list[str],
    send_levels: list[int],
    repo: VerifierRepo,
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
        node_b64 = verifier_repo_get_node(repo, level, pos)
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
    repo: VerifierRepo,
) -> tuple[bool, list[str], VerifierRepo]:
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
        known_node_b64 = verifier_repo_get_node(repo, trusted_level, i >> trusted_level)
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

    verifier_repo_store_proof(
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
    repo: VerifierRepo,
) -> tuple[bool, list[str], VerifierRepo]:
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


# ---------------------------------------------------------------------------
# Prover / Verifier orchestration classes
# ---------------------------------------------------------------------------


class ProverPaytreeFirstOpt:
    """Prover orchestration for PayTree first-opt: build tree, send root, send leaf sub-proofs.

    Receives a ProverRepo for tree storage; orchestration of crypto operations.
    """

    def __init__(self, repo: ProverRepo) -> None:
        self._repo = repo
        self._state: Optional[ProverState] = None

    def build_tree(self, leaves: list[bytes]) -> None:
        """Build Merkle tree from leaves and store in repo."""
        state = prover_build_tree(leaves)
        self._repo.clear()
        self._repo.update(state.repo)
        self._state = ProverState(
            root=state.root,
            repo=self._repo,
            tree_size=state.tree_size,
            depth=state.depth,
        )

    def get_root(self) -> tuple[bytes, int]:
        """Return Merkle root and tree size. Call build_tree first."""
        if self._state is None:
            raise ValueError("build_tree must be called before get_root")
        return prover_send_root(self._state)

    @property
    def depth(self) -> int:
        """Tree depth. Call build_tree first."""
        if self._state is None:
            raise ValueError("build_tree must be called before accessing depth")
        return self._state.depth

    def get_leaf_subproof_firstopt(
        self,
        leaf_index: int,
        already_sent_indexes: Optional[Iterable[int]] = None,
    ) -> tuple[int, int, bytes, list[bytes]]:
        """Return leaf sub-proof using first optimization."""
        if self._state is None:
            raise ValueError(
                "build_tree must be called before get_leaf_subproof_firstopt"
            )
        return prover_send_leaf_subproof_firstopt(
            self._state,
            leaf_index=leaf_index,
            already_sent_indexes=already_sent_indexes,
        )


class VerifierPaytreeFirstOpt:
    """Verifier orchestration for PayTree first-opt: save root, save leaf sub-proofs.

    Receives a VerifierRepoBytes for node storage; orchestration of crypto operations.
    """

    def __init__(self, repo: VerifierRepoBytes) -> None:
        self._repo = repo

    def save_root(self, root: bytes, tree_size: int) -> None:
        """Store Merkle root and tree size in repo."""
        verifier_receive_root(self._repo, root, tree_size)

    def save_leaf_subproof(
        self,
        leaf_index: int,
        leaf_hash: bytes,
        siblings: list[bytes],
    ) -> None:
        """Verify leaf sub-proof and store nodes in repo."""
        verifier_receive_leaf_subproof(
            self._repo, leaf_index=leaf_index, leaf_hash=leaf_hash, siblings=siblings
        )


# ---------------------------------------------------------------------------
# Client helper (PaytreeFirstOpt)
# ---------------------------------------------------------------------------


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
