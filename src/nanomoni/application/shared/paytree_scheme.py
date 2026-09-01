"""PayTree crypto schemes — one per proof mode.

These are orchestrators (they compose crypto primitives, the protocol layer and
shared verification helpers), so they live in the application layer rather than
in ``crypto`` — keeping ``crypto`` a pure, dependency-free bottom layer.
"""

from __future__ import annotations

from typing import Optional

from nanomoni.application.shared.paytree_proof import (
    verify_paytree_child_pair_payment,
    verify_paytree_proof_first_opt_collecting_path,
    verify_paytree_proof_standard,
)
from nanomoni.crypto.merkle_index import (
    get_ancestor_at_level,
    get_sibling_position_at_level,
    key_eytzinger,
)
from nanomoni.crypto.paytree import bytes_to_b64
from nanomoni.domain.shared.crypto_proof import CryptoProof
from nanomoni.domain.shared.proof_reference import ProofReference
from nanomoni.protocol import infer_subroot_index_for_incoming_pruned_merkle_proof


class PaytreeStdCryptoScheme:
    """Stateless verifier for standard (full leaf→root) PayTree proofs."""

    def verify(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
    ) -> bool:
        return verify_paytree_proof_standard(
            i=reference.value,
            leaf_b64=proof.data["leaf_b64"],
            siblings_b64=proof.data["siblings_b64"],
            root_b64=commitment,
            max_i=int(proof.data["max_steps"]),
        )


class PaytreeFirstOptCryptoScheme:
    """Stateless verifier for first-opt (pruned leaf→sub-root) PayTree proofs.

    Takes the sub-root/root node values as an already-read ``nodes`` argument —
    same pattern as ``commitment`` on ``PaytreeStdCryptoScheme`` — rather than
    fetching them itself. The caller (which already reads the node store once
    up front to derive the channel) owns sourcing and freshness of ``nodes``.

    Persists only the received leaf and siblings (P). Independent of
    ``PaytreeSecondOptCryptoScheme`` (no shared base class between them) —
    that scheme additionally persists the computed ancestor hashes from
    verification (Q); this one does not.
    """

    def verify(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
        nodes: dict[str, str],
    ) -> bool:
        i = reference.value
        leaf_b64: str = proof.data["leaf_b64"]
        siblings_b64: list[str] = proof.data["siblings_b64"]
        max_steps: int = int(proof.data["max_steps"])

        depth = max_steps.bit_length() if max_steps > 0 else 0
        root_key = key_eytzinger(depth, 0, depth)
        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            i, len(siblings_b64), depth
        )

        subroot_b64 = nodes.get(subroot_index, "")
        root_b64 = nodes.get(root_key, "") or commitment

        if not subroot_b64 and subroot_index == root_key:
            subroot_b64 = root_b64

        # An empty-siblings proof is only legitimate when the trusted leaf node
        # (0, i) is already present in the node store (persisted by a prior
        # verified payment). Never fall back to the client-supplied leaf_b64:
        # doing so would trust an unverified value that is not bound to the
        # channel commitment, allowing a forged leaf to pass verification.
        if not subroot_b64:
            return False

        return (
            verify_paytree_proof_first_opt_collecting_path(
                i=i,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
                subroot_b64=subroot_b64,
                subroot_index=subroot_index,
                depth=depth,
            )
            is not None
        )

    def build_node_updates(
        self,
        leaf_index: int,
        leaf_b64: str,
        siblings_b64: list[str],
        depth: int,
    ) -> dict[str, str]:
        """Build node_key → hash_b64 updates from a verified first-opt proof:
        the received leaf and siblings (P) only."""
        updates: dict[str, str] = {}
        updates[key_eytzinger(0, leaf_index, depth)] = leaf_b64
        for level, sib_b64 in enumerate(siblings_b64):
            pos = get_sibling_position_at_level(leaf_index, level)
            updates[key_eytzinger(level, pos, depth)] = sib_b64
        return updates


class PaytreeSecondOptCryptoScheme:
    """Stateless verifier for second-opt (pruned leaf→sub-root) PayTree proofs.

    Same wire protocol and verification as ``PaytreeFirstOptCryptoScheme``,
    duplicated here rather than shared/inherited (the two schemes are
    intentionally independent classes). The difference is
    ``build_node_updates``: this scheme also persists the ancestor hashes
    computed while verifying (Q), not just the received leaf/siblings (P).
    """

    def verify_collecting_path(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
        nodes: dict[str, str],
    ) -> Optional[list[bytes]]:
        """Verify a second-opt proof, returning every ancestor hash computed
        while climbing from the leaf to the sub-root (one per level) on
        success, or None if verification fails.

        `verify` and `build_node_updates` both derive from this single pass —
        the hash chain is walked exactly once per payment; the caller reuses
        its output rather than re-verifying to obtain the same hashes.
        """
        i = reference.value
        leaf_b64: str = proof.data["leaf_b64"]
        siblings_b64: list[str] = proof.data["siblings_b64"]
        max_steps: int = int(proof.data["max_steps"])

        depth = max_steps.bit_length() if max_steps > 0 else 0
        root_key = key_eytzinger(depth, 0, depth)
        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            i, len(siblings_b64), depth
        )

        subroot_b64 = nodes.get(subroot_index, "")
        root_b64 = nodes.get(root_key, "") or commitment

        if not subroot_b64 and subroot_index == root_key:
            subroot_b64 = root_b64

        # An empty-siblings proof is only legitimate when the trusted leaf node
        # (0, i) is already present in the node store (persisted by a prior
        # verified payment). Never fall back to the client-supplied leaf_b64:
        # doing so would trust an unverified value that is not bound to the
        # channel commitment, allowing a forged leaf to pass verification.
        if not subroot_b64:
            return None

        return verify_paytree_proof_first_opt_collecting_path(
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            subroot_b64=subroot_b64,
            subroot_index=subroot_index,
            depth=depth,
        )

    def verify(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
        nodes: dict[str, str],
    ) -> bool:
        return (
            self.verify_collecting_path(commitment, reference, proof, nodes) is not None
        )

    def build_node_updates(
        self,
        leaf_index: int,
        leaf_b64: str,
        siblings_b64: list[str],
        depth: int,
        computed_path: list[bytes],
    ) -> dict[str, str]:
        """Build node_key → hash_b64 updates from a verified second-opt proof.

        Stores the incoming leaf and siblings (P), plus every ancestor hash
        the verification step already computed while climbing from the leaf
        to the sub-root (Q): those are the same hashes
        `verify_collecting_path` returned, not recomputed here.
        """
        updates: dict[str, str] = {}
        updates[key_eytzinger(0, leaf_index, depth)] = leaf_b64
        for level, sib_b64 in enumerate(siblings_b64):
            pos = get_sibling_position_at_level(leaf_index, level)
            updates[key_eytzinger(level, pos, depth)] = sib_b64
        for offset, node_hash in enumerate(computed_path):
            level = offset + 1
            pos = get_ancestor_at_level(leaf_index, level)
            updates[key_eytzinger(level, pos, depth)] = bytes_to_b64(node_hash)
        return updates


class PaytreeChildPairCryptoScheme:
    """Stateless verifier for child-pair PayTree proofs (heap-indexed child reveal).

    Unlike `PaytreeStdCryptoScheme`/`PaytreeFirstOptCryptoScheme`, verification
    is against the already-known parent node hash (looked up by the caller
    from the node store), not the channel commitment/root directly — the root
    is only ever used to seed node 1 on the first payment.
    """

    def verify(self, known_parent_b64: str, left_b64: str, right_b64: str) -> bool:
        return verify_paytree_child_pair_payment(
            known_parent_b64=known_parent_b64,
            left_b64=left_b64,
            right_b64=right_b64,
        )

    def build_node_updates(
        self, k: int, left_b64: str, right_b64: str
    ) -> dict[str, str]:
        """Build node_key → hash_b64 updates for the two newly revealed children of k."""
        return {str(2 * k): left_b64, str(2 * k + 1): right_b64}
