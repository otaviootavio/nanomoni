"""Unit tests for PaytreeFirstOptCryptoScheme.build_node_updates (P only).

verify()'s bool contract is covered separately in
test_paytree_scheme_verify_bool_contract.py. PaytreeSecondOptCryptoScheme
(P+Q) is an independent class with its own tests in
test_paytree_second_opt_scheme.py.
"""

from __future__ import annotations

from nanomoni.application.shared.paytree_scheme import PaytreeFirstOptCryptoScheme
from nanomoni.crypto.merkle_index import get_sibling_position_at_level, key_eytzinger
from nanomoni.crypto.merkle_tree import build_merkle_tree, hash_bytes
from nanomoni.crypto.paytree import bytes_to_b64

MAX_STEPS = 7  # 8 leaves -> depth 3
DEPTH = 3


def _build_tree() -> tuple[bytes, list[list[bytes]]]:
    leaves = [hash_bytes(f"leaf{i}".encode()) for i in range(8)]
    return build_merkle_tree(leaves)


def _full_proof_for_leaf0(
    tree_levels: list[list[bytes]],
) -> tuple[str, list[str]]:
    """Full pruned proof for leaf 0 (all 3 siblings, sub-root = root)."""
    leaf_b64 = bytes_to_b64(tree_levels[0][0])
    siblings_b64 = [
        bytes_to_b64(tree_levels[level][get_sibling_position_at_level(0, level)])
        for level in range(DEPTH)
    ]
    return leaf_b64, siblings_b64


class TestBuildNodeUpdates:
    def test_build_node_updates_is_p_only(self) -> None:
        _root, tree_levels = _build_tree()
        leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
        scheme = PaytreeFirstOptCryptoScheme()

        updates = scheme.build_node_updates(0, leaf_b64, siblings_b64, DEPTH)

        assert updates == {
            key_eytzinger(0, 0, DEPTH): leaf_b64,
            key_eytzinger(0, 1, DEPTH): siblings_b64[0],
            key_eytzinger(1, 1, DEPTH): siblings_b64[1],
            key_eytzinger(2, 1, DEPTH): siblings_b64[2],
        }
        assert len(updates) == 4
