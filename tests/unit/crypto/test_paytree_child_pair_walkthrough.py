"""Walkthrough of the PayTree child-pair protocol against the worked example.

Mirrors the step-by-step example from the protocol write-up: an 8-leaf tree
(h1 = root; h2, h3 = children of root; ...; h8..h15 = leaves). Payment k
reveals the children of h_k; the vendor only ever needs nodes it already
accumulated (no path back to the root is re-sent). Closing sends the most
recently revealed child pair plus outer siblings up to the root.
"""

from __future__ import annotations

from nanomoni.crypto.merkle_tree import build_merkle_tree, hash_bytes
from nanomoni.crypto.paytree_child_pair import (
    children_of_k,
    max_k_for_depth,
    node_hash_at_k,
)
from nanomoni.protocol import (
    build_child_pair_close_proof,
    verify_child_pair_close_proof,
    verify_child_pair_payment,
)

LEAF_SECRETS: tuple[bytes, ...] = tuple(f"leaf{i}".encode() for i in range(8))
NUM_LEAVES = len(LEAF_SECRETS)
DEPTH = (NUM_LEAVES).bit_length() - 1  # 3


def _build_tree() -> tuple[bytes, list[list[bytes]]]:
    leaves = [hash_bytes(s) for s in LEAF_SECRETS]
    return build_merkle_tree(leaves)


def test_max_k_matches_number_of_internal_nodes() -> None:
    # 8 leaves -> 7 internal nodes (h1..h7), each revealed by one payment.
    assert max_k_for_depth(DEPTH) == 7


def test_children_of_k_matches_eytzinger_heap_numbering() -> None:
    assert children_of_k(1) == (2, 3)
    assert children_of_k(2) == (4, 5)
    assert children_of_k(3) == (6, 7)
    assert children_of_k(4) == (8, 9)


def test_child_pair_payments_and_progressive_close_examples() -> None:
    """Reproduces payments 1-4 and their corresponding close proofs verbatim."""
    root, tree_levels = _build_tree()

    def h(k: int) -> bytes:
        return node_hash_at_k(tree_levels, DEPTH, k)

    known: dict[int, bytes] = {1: root}

    # --- Payment 1: client sends (h2, h3) ---
    left, right = h(2), h(3)
    assert verify_child_pair_payment(known[1], left, right)
    known[2], known[3] = left, right

    # Close here: send (h2, h3); issuer checks H(h2,h3) == h1.
    close_left, close_right, siblings = build_child_pair_close_proof(1, known)
    assert (close_left, close_right, siblings) == (h(2), h(3), [])
    assert verify_child_pair_close_proof(root, 1, close_left, close_right, siblings)

    # --- Payment 2: client sends (h4, h5) ---
    left, right = h(4), h(5)
    assert verify_child_pair_payment(known[2], left, right)
    known[4], known[5] = left, right

    # Close here: send (h4, h5, h3); issuer computes h2=H(h4,h5), checks H(h2,h3)==h1.
    close_left, close_right, siblings = build_child_pair_close_proof(2, known)
    assert (close_left, close_right, siblings) == (h(4), h(5), [h(3)])
    assert verify_child_pair_close_proof(root, 2, close_left, close_right, siblings)

    # --- Payment 3: client sends (h6, h7) ---
    left, right = h(6), h(7)
    assert verify_child_pair_payment(known[3], left, right)
    known[6], known[7] = left, right

    # Close here: send (h2, h6, h7); issuer computes h3=H(h6,h7), checks H(h2,h3)==h1.
    close_left, close_right, siblings = build_child_pair_close_proof(3, known)
    assert (close_left, close_right, siblings) == (h(6), h(7), [h(2)])
    assert verify_child_pair_close_proof(root, 3, close_left, close_right, siblings)

    # --- Payment 4: client sends (h8, h9) ---
    left, right = h(8), h(9)
    assert verify_child_pair_payment(known[4], left, right)
    known[8], known[9] = left, right

    # Close here: send (h8, h9, h5, h3); issuer computes h4=H(h8,h9),
    # then h2=H(h4,h5), then checks H(h2,h3)==h1.
    close_left, close_right, siblings = build_child_pair_close_proof(4, known)
    assert (close_left, close_right, siblings) == (h(8), h(9), [h(5), h(3)])
    assert verify_child_pair_close_proof(root, 4, close_left, close_right, siblings)


def test_full_bfs_payment_sequence_verifies_and_recovers_root() -> None:
    """All payments 1..max_k verify in Eytzinger (BFS) order, using only known nodes."""
    root, tree_levels = _build_tree()
    max_k = max_k_for_depth(DEPTH)

    known: dict[int, bytes] = {1: root}
    for k in range(1, max_k + 1):
        left_k, right_k = children_of_k(k)
        left = node_hash_at_k(tree_levels, DEPTH, left_k)
        right = node_hash_at_k(tree_levels, DEPTH, right_k)
        assert verify_child_pair_payment(known[k], left, right)
        known[left_k], known[right_k] = left, right

        close_left, close_right, siblings = build_child_pair_close_proof(k, known)
        assert verify_child_pair_close_proof(root, k, close_left, close_right, siblings)


def test_verify_child_pair_payment_rejects_wrong_children() -> None:
    root, tree_levels = _build_tree()
    wrong_left = node_hash_at_k(tree_levels, DEPTH, 4)  # not a child of root
    wrong_right = node_hash_at_k(tree_levels, DEPTH, 5)
    assert not verify_child_pair_payment(root, wrong_left, wrong_right)


def test_verify_close_proof_rejects_tampered_sibling() -> None:
    root, tree_levels = _build_tree()
    left = node_hash_at_k(tree_levels, DEPTH, 4)
    right = node_hash_at_k(tree_levels, DEPTH, 5)
    tampered_sibling = hash_bytes(b"not-h3")
    assert not verify_child_pair_close_proof(root, 2, left, right, [tampered_sibling])
