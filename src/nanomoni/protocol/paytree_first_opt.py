"""PayTree first-opt protocol: pruned proof (leaf -> sub-root) per payment."""

from __future__ import annotations

from nanomoni.crypto.merkle_index import (
    get_ancestor_at_level,
    key_eytzinger,
)

# ``proof_indexes_first_opt`` is pure tree/index math and lives in the crypto
# layer (alongside the tree primitives it composes). It is re-exported here so
# that ``nanomoni.protocol`` remains the public entry point for first-opt flows.
from nanomoni.crypto.merkle_tree import proof_indexes_first_opt

__all__ = [
    "infer_subroot_index_for_incoming_pruned_merkle_proof",
    "proof_indexes_first_opt",
]


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
