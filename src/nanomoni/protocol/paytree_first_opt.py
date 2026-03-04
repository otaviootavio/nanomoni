"""PayTree first-opt protocol: pruned proof (leaf -> sub-root) per payment."""

from __future__ import annotations

from nanomoni.crypto.merkle_index import get_ancestor_at_level, lca_between
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
)


def proof_indexes_first_opt(
    leaf_index: int,
    prior_leaves: list[int],
    depth: int,
) -> list[tuple[int, int]]:
    """Return sibling indexes (level, position) for a pruned proof (leaf -> sub-root).

    Uses LCA with prior leaves to determine the sub-root. The upper level fetches
    secret and sibling hashes from storage using these indexes.
    """
    k_max = max((lca_between(leaf_index, a, depth) for a in prior_leaves), default=-1)
    ancestor_level = depth if k_max == 0 else depth - k_max - 1
    ancestor_pos = get_ancestor_at_level(leaf_index, ancestor_level)

    return build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, leaf_index, ancestor_level, ancestor_pos
    )
