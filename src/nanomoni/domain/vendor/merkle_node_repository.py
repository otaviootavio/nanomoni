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
    ) -> None: ...

    async def delete(self, channel_id: str) -> int: ...
