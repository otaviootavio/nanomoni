"""In-memory repository for PayTree first-opt prover tree storage.

Single responsibility: store and retrieve Merkle tree nodes from the built tree.
Used by the prover to hold the full tree and generate proofs (leaf + siblings).

Keys: "level:position" (e.g. "0:3", "2:1"). Values: raw hash bytes.
"""

from __future__ import annotations

from typing import Optional

from .merkle_index import key


ProverRepo = dict[str, bytes]
"""In-memory prover repo: key (level:position) -> hash (bytes)."""


def store_tree(
    repo: ProverRepo,
    tree_levels: list[list[bytes]],
) -> None:
    """Populate repo from built Merkle tree levels."""
    repo.clear()
    for level, row in enumerate(tree_levels):
        for position, h in enumerate(row):
            repo[key(level, position)] = h


def get_node(repo: ProverRepo, level: int, position: int) -> Optional[bytes]:
    """Get node hash by level and position. Returns None if not found."""
    return repo.get(key(level, position))
