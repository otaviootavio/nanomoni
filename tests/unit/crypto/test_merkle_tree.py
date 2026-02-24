"""Unit tests for merkle_tree (hashing, build, verify) with hardcoded values.

Concepts verified: build (Hash(left, right) per internal node), verification
(recompute root from leaf upward; hash order by left/right child).
"""

import hashlib

import pytest

from nanomoni.crypto.merkle_tree import (
    build_merkle_tree,
    combine_children,
    hash_bytes,
    verify_proof_to_known_node,
)

# Hardcoded SHA-256 digests for reproducible tests.
# In Merkle tree we hash hashes: parent = H(left_hash || right_hash).
# echo -n "a" | sha256sum
HASH_A = bytes.fromhex(
    "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
)
# echo -n "b" | sha256sum
HASH_B = bytes.fromhex(
    "3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d"
)
# echo -n "c" | sha256sum
HASH_C = bytes.fromhex(
    "2e7d2c03a9507ae265ecf5b5356885a53393a2029d241394997265a1a25aefc6"
)
# Parent of two leaf hashes: H(HASH_A || HASH_B)
HASH_AB = hashlib.sha256(HASH_A + HASH_B).digest()
# H(HASH_B || HASH_A)
HASH_BA = hashlib.sha256(HASH_B + HASH_A).digest()


class TestHashBytes:
    """SHA-256 for leaf and internal node hashes."""

    def test_single_byte_a(self) -> None:
        assert hash_bytes(b"a") == HASH_A

    def test_single_byte_b(self) -> None:
        assert hash_bytes(b"b") == HASH_B

    def test_empty(self) -> None:
        out = hash_bytes(b"")
        assert len(out) == 32
        assert out == hashlib.sha256(b"").digest()


class TestCombineChildren:
    """Hash(N'_q, N_p) vs Hash(N_p, N'_q) depending on left/right child."""

    def test_left_then_right(self) -> None:
        assert combine_children(HASH_A, HASH_B, left_is_first=True) == HASH_AB

    def test_right_then_left(self) -> None:
        assert combine_children(HASH_A, HASH_B, left_is_first=False) == HASH_BA

    def test_order_matters(self) -> None:
        assert HASH_AB != HASH_BA


class TestBuildMerkleTree:
    """Internal nodes Hash(N_left, N_right); pad to power-of-two with dup last leaf."""

    def test_two_leaves(self) -> None:
        leaves = [HASH_A, HASH_B]
        root, tree_levels = build_merkle_tree(leaves)
        expected_root = HASH_AB
        assert root == expected_root
        assert len(tree_levels) == 2
        assert tree_levels[0] == [HASH_A, HASH_B]
        assert tree_levels[1] == [expected_root]
        assert tree_levels[1][0] == expected_root

    def test_four_leaves(self) -> None:
        leaves = [HASH_A, HASH_B, HASH_C, HASH_C]  # last dup for padding
        root, tree_levels = build_merkle_tree(leaves)
        # Level 0: A, B, C, C
        # Level 1: H(A||B), H(C||C)
        h_ab = hashlib.sha256(HASH_A + HASH_B).digest()
        h_cc = hashlib.sha256(HASH_C + HASH_C).digest()
        expected_root = hashlib.sha256(h_ab + h_cc).digest()
        assert root == expected_root
        assert len(tree_levels) == 3
        assert tree_levels[0] == leaves
        assert tree_levels[1][0] == h_ab
        assert tree_levels[1][1] == h_cc
        assert tree_levels[2][0] == expected_root

    def test_one_leaf_padded_to_one(self) -> None:
        leaves = [HASH_A]
        root, tree_levels = build_merkle_tree(leaves)
        # Padded to 1 (no padding), single node is root
        assert root == HASH_A
        assert len(tree_levels) == 1
        assert tree_levels[0] == [HASH_A]

    def test_three_leaves_padded_to_four(self) -> None:
        leaves = [HASH_A, HASH_B, HASH_C]
        root, tree_levels = build_merkle_tree(leaves)
        # Padded: A, B, C, C
        assert len(tree_levels[0]) == 4
        assert tree_levels[0][3] == HASH_C
        # Root = H( H(A||B), H(C||C) )
        h_ab = hashlib.sha256(HASH_A + HASH_B).digest()
        h_cc = hashlib.sha256(HASH_C + HASH_C).digest()
        expected_root = hashlib.sha256(h_ab + h_cc).digest()
        assert root == expected_root

    def test_empty_leaves_raises(self) -> None:
        with pytest.raises(
            ValueError, match="Cannot build Merkle tree with empty leaves"
        ):
            build_merkle_tree([])


class TestVerifyProofToKnownNode:
    """Recompute root from leaf using auth path; success iff match."""

    def test_verify_leaf0_to_root_two_leaves(self) -> None:
        # Tree: leaves [A, B], root = H(A||B). Proof for index 0: leaf A, sibling B.
        leaf_hash = HASH_A
        leaf_index = 0
        siblings = [HASH_B]
        known_node_hash = HASH_AB
        known_node_level = 1
        assert (
            verify_proof_to_known_node(
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
                siblings=siblings,
                known_node_hash=known_node_hash,
                known_node_level=known_node_level,
            )
            is True
        )

    def test_verify_leaf1_to_root_two_leaves(self) -> None:
        # Index 1 is right child; sibling is left. Parent = Hash(left, right) = H(A||B).
        # left_is_first=False gives H(sibling||current) = H(A||B).
        leaf_hash = HASH_B
        leaf_index = 1
        siblings = [HASH_A]
        known_node_hash = HASH_AB
        known_node_level = 1
        assert (
            verify_proof_to_known_node(
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
                siblings=siblings,
                known_node_hash=known_node_hash,
                known_node_level=known_node_level,
            )
            is True
        )

    def test_wrong_sibling_rejects(self) -> None:
        leaf_hash = HASH_A
        leaf_index = 0
        siblings = [HASH_C]  # wrong sibling
        known_node_hash = HASH_AB
        known_node_level = 1
        assert (
            verify_proof_to_known_node(
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
                siblings=siblings,
                known_node_hash=known_node_hash,
                known_node_level=known_node_level,
            )
            is False
        )

    def test_wrong_known_node_rejects(self) -> None:
        leaf_hash = HASH_A
        leaf_index = 0
        siblings = [HASH_B]
        known_node_hash = HASH_BA  # wrong root
        known_node_level = 1
        assert (
            verify_proof_to_known_node(
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
                siblings=siblings,
                known_node_hash=known_node_hash,
                known_node_level=known_node_level,
            )
            is False
        )

    def test_sibling_count_mismatch_returns_false(self) -> None:
        leaf_hash = HASH_A
        leaf_index = 0
        siblings: list[bytes] = []  # need 1
        known_node_hash = HASH_AB
        known_node_level = 1
        assert (
            verify_proof_to_known_node(
                leaf_hash=leaf_hash,
                leaf_index=leaf_index,
                siblings=siblings,
                known_node_hash=known_node_hash,
                known_node_level=known_node_level,
            )
            is False
        )

    def test_negative_leaf_index_returns_false(self) -> None:
        assert (
            verify_proof_to_known_node(
                leaf_hash=HASH_A,
                leaf_index=-1,
                siblings=[HASH_B],
                known_node_hash=HASH_AB,
                known_node_level=1,
            )
            is False
        )
