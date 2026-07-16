"""PaywordCryptoScheme — wraps PayWord hash-chain proof verification."""

from __future__ import annotations

from ..crypto.payword import (
    b64_to_bytes,
    verify_token_against_root,
    verify_token_incremental,
)
from ..domain.shared.proof_reference import ProofReference
from .scheme import CryptoProof


class PaywordCryptoScheme:
    """Stateless PayWord verifier.

    For incremental verification (subsequent payments) the caller must include
    proof.data["prev_token_b64"] and proof.data["delta_k"]; otherwise the scheme
    falls back to root-based verification.
    """

    def extract_reference(self, proof: CryptoProof) -> ProofReference:
        return ProofReference(value=int(proof.data["k"]))

    async def verify(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
    ) -> bool:
        k = reference.value
        try:
            token = b64_to_bytes(proof.data["token_b64"])
        except Exception:
            return False

        prev_token_b64 = proof.data.get("prev_token_b64")
        delta_k = proof.data.get("delta_k")

        if prev_token_b64 is None or delta_k is None:
            try:
                root = b64_to_bytes(commitment)
            except Exception:
                return False
            return verify_token_against_root(token=token, k=k, root=root)

        if int(delta_k) <= 0:
            return False

        try:
            prev_token = b64_to_bytes(prev_token_b64)
        except Exception:
            return False

        return verify_token_incremental(
            token=token, prev_token=prev_token, delta_k=int(delta_k)
        )
