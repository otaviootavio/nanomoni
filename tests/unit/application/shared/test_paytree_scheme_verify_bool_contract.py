"""Standalone regression battery for PaytreeFirstOptCryptoScheme.verify's bool contract.

``verify`` is now a thin wrapper over ``verify_collecting_path``
(``verify_collecting_path(...) is not None``). This file exercises ``verify``
alone -- never referencing ``verify_collecting_path`` -- with hardcoded
``True``/``False`` outcomes, so a future change to the wrapper that breaks the
public bool contract (e.g. returning something other than a strict bool) is
caught here independently of the richer tests in ``test_paytree_scheme.py``.
"""

from __future__ import annotations

from nanomoni.application.shared.paytree_scheme import PaytreeFirstOptCryptoScheme
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


def _full_proof_for_leaf0(tree_levels: list[list[bytes]]) -> tuple[str, list[str]]:
    """Full pruned proof for leaf 0 (all 3 siblings, sub-root = root)."""
    leaf_b64 = bytes_to_b64(tree_levels[0][0])
    siblings_b64 = [
        bytes_to_b64(tree_levels[level][get_sibling_position_at_level(0, level)])
        for level in range(DEPTH)
    ]
    return leaf_b64, siblings_b64


def test_valid_full_proof_returns_true() -> None:
    root, tree_levels = _build_tree()
    commitment_b64 = bytes_to_b64(root)
    leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        commitment_b64, ProofReference(value=0), _make_proof(leaf_b64, siblings_b64), {}
    )

    assert result is True


def test_forged_leaf_returns_false() -> None:
    root, tree_levels = _build_tree()
    commitment_b64 = bytes_to_b64(root)
    _real_leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
    forged_leaf_b64 = bytes_to_b64(hash_bytes(b"forged"))
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        commitment_b64,
        ProofReference(value=0),
        _make_proof(forged_leaf_b64, siblings_b64),
        {},
    )

    assert result is False


def test_tampered_sibling_returns_false() -> None:
    root, tree_levels = _build_tree()
    commitment_b64 = bytes_to_b64(root)
    leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
    tampered = bytearray(b64_to_bytes(siblings_b64[1]))
    tampered[0] ^= 0xFF
    siblings_b64[1] = bytes_to_b64(bytes(tampered))
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        commitment_b64, ProofReference(value=0), _make_proof(leaf_b64, siblings_b64), {}
    )

    assert result is False


def test_empty_siblings_known_leaf_returns_true() -> None:
    root, tree_levels = _build_tree()
    commitment_b64 = bytes_to_b64(root)
    leaf1_b64 = bytes_to_b64(tree_levels[0][1])
    nodes = {key_eytzinger(0, 1, DEPTH): leaf1_b64}
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        commitment_b64, ProofReference(value=1), _make_proof(leaf1_b64, []), nodes
    )

    assert result is True


def test_empty_siblings_unknown_leaf_returns_false() -> None:
    root, tree_levels = _build_tree()
    commitment_b64 = bytes_to_b64(root)
    leaf1_b64 = bytes_to_b64(tree_levels[0][1])
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        commitment_b64, ProofReference(value=1), _make_proof(leaf1_b64, []), {}
    )

    assert result is False


def test_wrong_commitment_returns_false() -> None:
    _root, tree_levels = _build_tree()
    leaf_b64, siblings_b64 = _full_proof_for_leaf0(tree_levels)
    wrong_commitment_b64 = bytes_to_b64(hash_bytes(b"different-root"))
    scheme = PaytreeFirstOptCryptoScheme()

    result = scheme.verify(
        wrong_commitment_b64,
        ProofReference(value=0),
        _make_proof(leaf_b64, siblings_b64),
        {},
    )

    assert result is False
