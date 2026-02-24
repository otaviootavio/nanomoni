"""Prover logic for PayTree first-opt protocol.

Prover is stateless: does crypto and path computations only. No internal repository.
Receives tree_levels (or reads from ProverRepo) for proof generation.
Composed flow: root, tree_levels = prover.build_tree(leaves); prover_repo.store_tree(tree_levels);
              leaf_index, ts, lh, sibs = prover.get_leaf_subproof_firstopt(tree_levels, ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ...crypto.merkle_index import (
    compute_lcp,
    get_sibling_position_at_level,
)
from ...crypto.merkle_tree import build_merkle_tree


def _get_node(tree_levels: list[list[bytes]], level: int, position: int) -> bytes:
    """Get node hash at (level, position) from tree_levels."""
    row = tree_levels[level]
    if position >= len(row):
        raise ValueError(f"Position {position} out of range for level {level}")
    return row[position]


@dataclass(frozen=True)
class ProverState:
    """Prover state: built tree (in-memory) for path computations."""

    root: bytes
    tree_size: int  # number of leaves (max_i + 1)
    depth: int
    tree_levels: list[list[bytes]]


# ---------------------------------------------------------------------------
# Prover (stateless: crypto + index operations)
# ---------------------------------------------------------------------------


class Prover:
    """Stateless prover: crypto and path computations. Receives tree_levels as param."""

    @staticmethod
    def build_tree(leaves: list[bytes]) -> tuple[bytes, int, list[list[bytes]]]:
        """Build Merkle tree from leaves. Returns (root, tree_size, tree_levels)."""
        if not leaves:
            raise ValueError("Cannot build Merkle tree with empty leaves")
        root, tree_levels = build_merkle_tree(leaves)
        tree_size = len(tree_levels[0])
        return root, tree_size, tree_levels

    @staticmethod
    def get_root(tree_levels: list[list[bytes]]) -> tuple[bytes, int]:
        """Return Merkle root and tree size from tree_levels."""
        if not tree_levels:
            raise ValueError("tree_levels cannot be empty")
        root = tree_levels[-1][0]
        tree_size = len(tree_levels[0])
        return root, tree_size

    @staticmethod
    def get_leaf_subproof_firstopt(
        tree_levels: list[list[bytes]],
        leaf_index: int,
        already_sent_indexes: Optional[Iterable[int]] = None,
    ) -> tuple[int, int, bytes, list[bytes]]:
        """Prover sends leaf X (index, tree size) and its pruned sub-proof using first optimization.

        First optimization: omit sibling hashes at levels above n - k_max - 1.
        Returns (leaf_index, tree_size, leaf_hash, siblings).
        """
        tree_size = len(tree_levels[0])
        depth = len(tree_levels) - 1
        if leaf_index < 0 or leaf_index >= tree_size:
            raise ValueError(f"Leaf index {leaf_index} out of range [0, {tree_size})")
        if already_sent_indexes is None:
            send_levels = list(range(depth))
        else:
            indexes = list(already_sent_indexes)
            if not indexes:
                send_levels = list(range(depth))
            else:
                k_max = max(compute_lcp(leaf_index, a, depth) for a in indexes)
                send_levels = list(range(max(0, depth - k_max)))
        leaf_hash = _get_node(tree_levels, 0, leaf_index)
        siblings = [
            _get_node(
                tree_levels, level, get_sibling_position_at_level(leaf_index, level)
            )
            for level in send_levels
        ]
        return leaf_index, tree_size, leaf_hash, siblings


# ---------------------------------------------------------------------------
# Legacy functions (delegate to Prover)
# ---------------------------------------------------------------------------


def prover_build_tree(leaves: list[bytes]) -> ProverState:
    """Prover generates Merkle tree from leaves. Returns ProverState."""
    root, tree_size, tree_levels = Prover.build_tree(leaves)
    depth = len(tree_levels) - 1
    return ProverState(
        root=root,
        tree_size=tree_size,
        depth=depth,
        tree_levels=tree_levels,
    )


def prover_send_root(state: ProverState) -> tuple[bytes, int]:
    """Prover sends Merkle root and tree size to verifier."""
    return state.root, state.tree_size


def prover_send_leaf_subproof_firstopt(
    state: ProverState,
    leaf_index: int,
    already_sent_indexes: Optional[Iterable[int]] = None,
) -> tuple[int, int, bytes, list[bytes]]:
    """Prover sends leaf X (index, tree size) and its pruned sub-proof. Delegates to Prover."""
    return Prover.get_leaf_subproof_firstopt(
        state.tree_levels, leaf_index, already_sent_indexes
    )


class ProverPaytreeFirstOpt:
    """Prover orchestration for PayTree first-opt: build tree, send root, send leaf sub-proofs.

    Crypto and path computations only. No internal repository.
    Tree is held in memory. Caller persists via repository if needed.
    """

    def __init__(self) -> None:
        self._state: Optional[ProverState] = None

    def build_tree(self, leaves: list[bytes]) -> None:
        """Build Merkle tree from leaves. Tree held in memory for proof generation."""
        self._state = prover_build_tree(leaves)

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
