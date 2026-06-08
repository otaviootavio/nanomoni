"""PayTree first-opt protocol: pruned proof (leaf -> sub-root) per payment."""

from __future__ import annotations

from nanomoni.crypto.merkle_index import (
    get_ancestor_at_level,
    key_eytzinger,
    lca_between,
)
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
)


def infer_subroot_index_for_incoming_pruned_merkle_proof(
    leaf_index: int,
    siblings_count: int,
    depth: int,
) -> str:
    """Infer sub-root Eytzinger key from the number of siblings received.

    When siblings_count=0: trusted node is the leaf (0, leaf_index).
    When siblings_count=k: sub-root at level k.
    """
    if siblings_count == 0:
        return key_eytzinger(0, leaf_index, depth)
    trusted_level = min(siblings_count, depth)
    trusted_pos = get_ancestor_at_level(leaf_index, trusted_level)
    return key_eytzinger(trusted_level, trusted_pos, depth)


def proof_indexes_first_opt(
    leaf_index: int,
    prior_leaves: list[int],
    depth: int,
) -> list[tuple[int, int]]:
    """Return sibling indexes (level, position) for a pruned proof (leaf -> sub-root).

    Uses LCA with the last prior leaf to determine the sub-root (for sequential
    sends the max LCP is with the immediate prior). The upper level fetches
    secret and sibling hashes from storage using these indexes.
    """
    last_prior = prior_leaves[-1] if prior_leaves else None
    k_max = lca_between(leaf_index, last_prior, depth) if last_prior is not None else -1
    ancestor_level = depth if k_max == 0 else depth - k_max - 1
    ancestor_pos = get_ancestor_at_level(leaf_index, ancestor_level)

    return build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, leaf_index, ancestor_level, ancestor_pos
    )
