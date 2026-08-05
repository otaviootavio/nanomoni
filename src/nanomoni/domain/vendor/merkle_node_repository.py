"""MerkleNodeRepository — sparse per-channel node store for first-opt PayTree proofs."""

from __future__ import annotations

from typing import Optional, Protocol

from ..shared.crypto_proof import CryptoProof
from .entities import PaymentChannel, PaymentState


class MerkleNodeRepository(Protocol):
    async def get_nodes(self, channel_id: str, keys: list[str]) -> dict[str, str]: ...

    async def get_channel_and_nodes(
        self,
        channel_id: str,
        read_keys: list[str],
    ) -> tuple[Optional[PaymentChannel], dict[str, str]]:
        """Read the channel (deserialized) and a batch of node keys in one round trip."""
        ...

    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None: ...

    async def save_nodes_and_payment(
        self,
        channel_id: str,
        node_updates: dict[str, str],
        new_ref: int,
        channel: PaymentChannel,
        state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[int]]:
        """Atomically save merkle nodes + channel/state/proof with a monotonic CAS.

        Serializes ``channel``/``state``/``proof`` internally (mirroring
        ``PaymentRepositoryImpl.save_payment``), so this cost is consistently
        attributed to the repository layer rather than the calling use case.

        Returns (status, stored_ref):
          1 = success (stored_ref = new_ref)
          0 = stale/not-increasing (stored_ref = current last_proof_reference)
          2 = no max_steps available for the channel
          3 = capacity exceeded (stored_ref = current last_proof_reference)
        """
        ...

    async def delete(self, channel_id: str) -> int: ...
