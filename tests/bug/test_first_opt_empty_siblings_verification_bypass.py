"""Regression test: first-opt Merkle verification bypass via empty siblings.

## The bug (CRITICAL)

``PaytreeFirstOptCryptoScheme.verify`` infers which node in the tree is the
"trusted" sub-root from the *client-controlled* ``len(siblings_b64)``:

    src/nanomoni/crypto/paytree_scheme.py

        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            i, len(siblings_b64), depth
        )
        subroot_b64 = nodes.get(subroot_index, "")
        ...
        if not subroot_b64 and subroot_index == key_eytzinger(0, i, depth):
            subroot_b64 = leaf_b64          # <-- trusts the client's own leaf

When a client sends ``siblings_b64 == []``, ``infer_...`` returns the leaf's
own Eytzinger key ``(0, i)``. For a *fresh* index ``i`` that leaf is not yet in
the vendor's node store, so ``nodes.get(...)`` is empty and the fallback sets
``subroot_b64 = leaf_b64`` -- i.e. the client's own supplied leaf becomes the
"trusted" node. ``verify_paytree_proof_first_opt`` then runs an empty-siblings
proof of ``leaf`` against ``leaf`` and trivially returns ``True``.

The proof is therefore accepted **without ever being connected to
``channel.commitment``**. A malicious client can pay with an arbitrary,
never-committed leaf and get the vendor to deliver service for a payment that
can never settle.

## Correct behaviour

Empty siblings are only legitimate when the leaf ``(0, i)`` is *already stored*
in the vendor's node store (put there by a prior verified payment). If the node
is absent, verification must reject -- exactly as the intermediate sub-root case
already does (``return False``). The commitment must always anchor the proof.

## Running

Pure crypto-scheme test -- no services required:

    poetry run pytest tests/bug/test_first_opt_empty_siblings_verification_bypass.py -v
"""

from __future__ import annotations

from nanomoni.crypto.merkle_index import key_eytzinger
from nanomoni.crypto.merkle_tree import build_merkle_tree, hash_bytes
from nanomoni.crypto.paytree import bytes_to_b64
from nanomoni.crypto.paytree_scheme import PaytreeFirstOptCryptoScheme
from nanomoni.crypto.scheme import CryptoProof
from nanomoni.domain.shared.proof_reference import PaymentScheme, ProofReference

# 8-leaf committed tree -> depth 3, max_steps (max leaf index) = 7.
LEAF_SECRETS: tuple[bytes, ...] = (
    b"leaf0",
    b"leaf1",
    b"leaf2",
    b"leaf3",
    b"leaf4",
    b"leaf5",
    b"leaf6",
    b"leaf7",
)
MAX_STEPS = len(LEAF_SECRETS) - 1  # 7
DEPTH = MAX_STEPS.bit_length()  # 3 -- matches scheme's own depth derivation

# Index the attacker pays with. Fresh -> node (0, i) is NOT in the vendor store.
ATTACK_INDEX = 3


def _committed_root_b64() -> str:
    """Build the real committed tree and return its root as base64."""
    leaf_hashes = [hash_bytes(s) for s in LEAF_SECRETS]
    root, _levels = build_merkle_tree(leaf_hashes)
    return bytes_to_b64(root)


def _forged_leaf_b64() -> str:
    """A leaf hash the client invents -- never part of the committed tree."""
    return bytes_to_b64(hash_bytes(b"attacker-forged-leaf-never-committed"))


def _make_proof(leaf_b64: str) -> CryptoProof:
    return CryptoProof(
        scheme=PaymentScheme.PAYTREE,
        data={
            "leaf_b64": leaf_b64,
            "siblings_b64": [],  # <-- the attack: no authentication path
            "max_steps": MAX_STEPS,
        },
    )


def test_empty_siblings_forged_leaf_is_rejected() -> None:
    """A forged leaf with empty siblings must NOT verify against the commitment.

    Reproduces the CRITICAL bypass: with the current code this returns ``True``
    (accepted), so this assertion FAILS until the leaf fallback in
    ``PaytreeFirstOptCryptoScheme.verify`` is removed/guarded.
    """
    scheme = PaytreeFirstOptCryptoScheme()
    commitment = _committed_root_b64()
    forged_leaf_b64 = _forged_leaf_b64()

    # Sanity: the forged leaf is genuinely not the real committed leaf at i.
    real_leaf_b64 = bytes_to_b64(hash_bytes(LEAF_SECRETS[ATTACK_INDEX]))
    assert forged_leaf_b64 != real_leaf_b64

    # Vendor's node store is empty for this fresh index: neither the root nor
    # the leaf (0, i) is present -- only the commitment anchors the proof.
    empty_nodes: dict[str, str] = {}

    accepted = scheme.verify(
        commitment,
        ProofReference(value=ATTACK_INDEX),
        _make_proof(forged_leaf_b64),
        nodes=empty_nodes,
    )

    assert accepted is False, (
        "VERIFICATION BYPASS: vendor accepted a forged leaf with empty siblings "
        "that is not bound to channel.commitment. The client's own leaf_b64 was "
        "trusted as the sub-root (crypto/paytree_scheme.py leaf fallback)."
    )


def test_empty_siblings_only_valid_when_leaf_already_stored() -> None:
    """Empty siblings is legitimate ONLY when node (0, i) is already in the store.

    This is the intended semantics and documents the correct fix boundary: when
    the leaf node has been persisted by a prior verified payment, an empty-proof
    payment for that same leaf is accepted; and a *different* leaf value is
    rejected because it mismatches the stored (committed) hash.
    """
    scheme = PaytreeFirstOptCryptoScheme()
    commitment = _committed_root_b64()

    real_leaf_b64 = bytes_to_b64(hash_bytes(LEAF_SECRETS[ATTACK_INDEX]))
    leaf_key = key_eytzinger(0, ATTACK_INDEX, DEPTH)

    # Store holds the genuine, committed leaf hash at (0, i).
    stored_nodes = {leaf_key: real_leaf_b64}

    # Same leaf with empty siblings -> accepted (matches the stored node).
    assert (
        scheme.verify(
            commitment,
            ProofReference(value=ATTACK_INDEX),
            _make_proof(real_leaf_b64),
            nodes=stored_nodes,
        )
        is True
    )

    # A forged leaf against the same stored node -> rejected (hash mismatch).
    assert (
        scheme.verify(
            commitment,
            ProofReference(value=ATTACK_INDEX),
            _make_proof(_forged_leaf_b64()),
            nodes=stored_nodes,
        )
        is False
    )
