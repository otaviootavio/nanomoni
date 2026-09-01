"""Unit tests for PaytreeSecondOptCryptoScheme's Q-storage behavior.

Independent class from PaytreeFirstOptCryptoScheme (no shared base) --
same wire protocol and verification, but its build_node_updates persists the
computed ancestor hashes from verification (Q) too, not just the received
leaf/siblings (P). See test_paytree_scheme.py for first-opt's P-only
build_node_updates and test_paytree_scheme_verify_bool_contract.py for the
shared bool-verify contract style.

Covers `verify_collecting_path` (returns every ancestor hash computed while
climbing from the leaf to the sub-root, reused by `build_node_updates` instead
of being recomputed) and `build_node_updates` (folds those computed hashes
alongside the received leaf/siblings into a single node-store update dict).
"""

from __future__ import annotations

from nanomoni.application.shared.paytree_scheme import PaytreeSecondOptCryptoScheme
from nanomoni.crypto.merkle_index import get_sibling_position_at_level, key_eytzinger
from nanomoni.crypto.merkle_tree import build_merkle_tree, hash_bytes
from nanomoni.crypto.paytree import b64_to_bytes, bytes_to_b64
from nanomoni.domain.shared.crypto_proof import CryptoProof
from nanomoni.domain.shared.proof_reference import PaymentScheme, ProofReference

MAX_STEPS = 7  # 8 leaves -> depth 3
DEPTH = 3


def _build_tree() -> tuple[bytes, list[list[bytes]]]:
    leaves = [hash_bytes(f"leaf{i}".encode()) for i in range(8)]
    return build_merkle_tree(leaves)


def _make_proof(leaf_b64: str, siblings_b64: list[str]) -> CryptoProof:
    return CryptoProof(
        scheme=PaymentScheme.PAYTREE,
        data={
            "leaf_b64": leaf_b64,
            "siblings_b64": siblings_b64,
            "max_steps": MAX_STEPS,
        },
    )


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


class TestVerifyCollectingPath:
    def test_full_proof_returns_correct_ancestor_chain(self) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
        scheme = PaytreeSecondOptCryptoScheme()

        result = scheme.verify_collecting_path(
            commitment_b64,
            ProofReference(value=0),
            _make_proof(leaf_b64, siblings_b64),
            {},
        )

        assert result == [tree_levels[1][0], tree_levels[2][0], tree_levels[3][0]]

    def test_empty_siblings_accepted_when_leaf_already_known_returns_empty_path(
        self,
    ) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf1_b64 = bytes_to_b64(tree_levels[0][1])
        nodes = {key_eytzinger(0, 1, DEPTH): leaf1_b64}
        scheme = PaytreeSecondOptCryptoScheme()

        result = scheme.verify_collecting_path(
            commitment_b64,
            ProofReference(value=1),
            _make_proof(leaf1_b64, []),
            nodes,
        )

        assert result == []

    def test_empty_siblings_rejected_when_leaf_unknown_returns_none(self) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf1_b64 = bytes_to_b64(tree_levels[0][1])
        scheme = PaytreeSecondOptCryptoScheme()

        result = scheme.verify_collecting_path(
            commitment_b64,
            ProofReference(value=1),
            _make_proof(leaf1_b64, []),
            {},
        )

        assert result is None

    def test_tampered_sibling_returns_none(self) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
        tampered = bytearray(b64_to_bytes(siblings_b64[1]))
        tampered[0] ^= 0xFF
        siblings_b64[1] = bytes_to_b64(bytes(tampered))
        scheme = PaytreeSecondOptCryptoScheme()

        result = scheme.verify_collecting_path(
            commitment_b64,
            ProofReference(value=0),
            _make_proof(leaf_b64, siblings_b64),
            {},
        )

        assert result is None

    def test_verify_bool_matches_collecting_path_is_not_none(self) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
        scheme = PaytreeSecondOptCryptoScheme()
        valid_proof = _make_proof(leaf_b64, siblings_b64)

        tampered_siblings = list(siblings_b64)
        tampered = bytearray(b64_to_bytes(tampered_siblings[1]))
        tampered[0] ^= 0xFF
        tampered_siblings[1] = bytes_to_b64(bytes(tampered))
        tampered_proof = _make_proof(leaf_b64, tampered_siblings)

        for proof in (valid_proof, tampered_proof):
            reference = ProofReference(value=0)
            assert scheme.verify(commitment_b64, reference, proof, {}) == (
                scheme.verify_collecting_path(commitment_b64, reference, proof, {})
                is not None
            )


class TestBuildNodeUpdates:
    def test_includes_both_received_and_computed_keys(self) -> None:
        root, tree_levels = _build_tree()
        commitment_b64 = bytes_to_b64(root)
        leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
        scheme = PaytreeSecondOptCryptoScheme()
        computed_path = scheme.verify_collecting_path(
            commitment_b64,
            ProofReference(value=0),
            _make_proof(leaf_b64, siblings_b64),
            {},
        )
        assert computed_path is not None

        updates = scheme.build_node_updates(
            0, leaf_b64, siblings_b64, DEPTH, computed_path
        )

        received = {
            key_eytzinger(0, 0, DEPTH): leaf_b64,
            key_eytzinger(0, 1, DEPTH): siblings_b64[0],
            key_eytzinger(1, 1, DEPTH): siblings_b64[1],
            key_eytzinger(2, 1, DEPTH): siblings_b64[2],
        }
        computed = {
            key_eytzinger(1, 0, DEPTH): bytes_to_b64(tree_levels[1][0]),
            key_eytzinger(2, 0, DEPTH): bytes_to_b64(tree_levels[2][0]),
            key_eytzinger(3, 0, DEPTH): bytes_to_b64(tree_levels[3][0]),
        }
        assert received.keys().isdisjoint(computed.keys())
        assert updates == {**received, **computed}
        assert len(updates) == 7
