"""In-memory prover tree storage for PayTree first-opt.

Dummy prover repo: stores nodes only. Keys: "level:position" (e.g. "0:3", "2:1").
Composed flow: root, tree_size, tree_levels = prover.build_tree(leaves);
              prover_repo.store_tree(tree_levels);
              leaf_index, ts, lh, sibs = prover.get_leaf_subproof_firstopt(tree_levels, ...)
"""

from __future__ import annotations

from typing import Optional

from ...crypto.merkle_index import key


def _store_tree(
    repo: dict[str, bytes],
    tree_levels: list[list[bytes]],
) -> None:
    """Populate repo from built Merkle tree levels."""
    repo.clear()
    for level, row in enumerate(tree_levels):
        for position, h in enumerate(row):
            repo[key(level, position)] = h


def _get_node(repo: dict[str, bytes], level: int, position: int) -> Optional[bytes]:
    """Get node hash by level and position. Returns None if not found."""
    return repo.get(key(level, position))


class ProverRepo(dict[str, bytes]):
    """Dummy prover repo: stores nodes only. No proof generation logic."""

    def store_tree(self, tree_levels: list[list[bytes]]) -> None:
        """Populate repo from built Merkle tree levels."""
        _store_tree(self, tree_levels)

    def get_node(self, level: int, position: int) -> Optional[bytes]:
        """Get node hash by level and position. Returns None if not found."""
        return _get_node(self, level, position)
