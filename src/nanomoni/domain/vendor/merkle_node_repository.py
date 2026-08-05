"""MerkleNodeRepository — sparse per-channel node store for first-opt PayTree proofs."""

from __future__ import annotations

from typing import Optional, Protocol


class MerkleNodeRepository(Protocol):
    async def get_nodes(self, channel_id: str, keys: list[str]) -> dict[str, str]: ...

    async def get_channel_and_nodes(
        self,
        channel_id: str,
        read_keys: list[str],
    ) -> tuple[Optional[str], dict[str, str]]: ...

    async def get_nodes_and_merge(
        self,
        channel_id: str,
        read_keys: list[str],
        updates: dict[str, str],
    ) -> dict[str, str]: ...

    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None: ...

    async def save_nodes_and_payment(
        self,
        channel_id: str,
        node_updates: dict[str, str],
        new_ref: int,
        channel_json: str,
        state_json: str,
        proof_json: str,
        is_closed: bool,
        created_at_ts: float,
    ) -> tuple[int, Optional[int]]:
        """Atomically save merkle nodes + channel/state/proof with a monotonic CAS.

        Returns (status, stored_ref):
          1 = success (stored_ref = new_ref)
          0 = stale/not-increasing (stored_ref = current last_proof_reference)
          2 = no max_steps available for the channel
          3 = capacity exceeded (stored_ref = current last_proof_reference)
        """
        ...

    async def delete(self, channel_id: str) -> int: ...
