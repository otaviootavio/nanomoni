"""PayTree crypto schemes — one per proof mode."""

from __future__ import annotations

from ..application.shared.paytree_proof import (
    verify_paytree_proof_first_opt,
    verify_paytree_proof_standard,
)
from ..crypto.merkle_index import (
    get_sibling_position_at_level,
    key_eytzinger,
)
from ..domain.shared.proof_reference import ProofReference
from ..protocol import infer_subroot_index_for_incoming_pruned_merkle_proof
from .scheme import CryptoProof


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
        if not subroot_b64 and subroot_index == key_eytzinger(0, i, depth):
            subroot_b64 = leaf_b64

        if not subroot_b64:
            return False

        return verify_paytree_proof_first_opt(
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            subroot_b64=subroot_b64,
            subroot_index=subroot_index,
            depth=depth,
        )

    def build_node_updates(
        self,
        leaf_index: int,
        leaf_b64: str,
        siblings_b64: list[str],
        depth: int,
    ) -> dict[str, str]:
        """Build node_key → hash_b64 updates from a verified first-opt proof."""
        updates: dict[str, str] = {}
        updates[key_eytzinger(0, leaf_index, depth)] = leaf_b64
        for level, sib_b64 in enumerate(siblings_b64):
            pos = get_sibling_position_at_level(leaf_index, level)
            updates[key_eytzinger(level, pos, depth)] = sib_b64
        return updates
