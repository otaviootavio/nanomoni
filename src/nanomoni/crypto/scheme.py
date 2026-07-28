from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..domain.shared.proof_reference import PaymentScheme, ProofReference


@dataclass
class CryptoProof:
    """Raw scheme-specific proof data.  Opaque above the crypto layer.

    PayTree (storage):  {"leaf_b64": str, "siblings_b64": list[str], "optimization_type": int}
    PayTree (verify):   above + {"max_steps": int}
    PayWord (storage):  {"token_b64": str}
    PayWord (verify):   above + {"prev_token_b64": str|None, "delta_k": int|None}
    """

    scheme: PaymentScheme
    data: dict[str, Any] = field(default_factory=dict)


class CryptoScheme(Protocol):
    async def verify(
        self,
        commitment: str,
        reference: ProofReference,
        proof: CryptoProof,
    ) -> bool: ...

    def extract_reference(self, proof: CryptoProof) -> ProofReference: ...
