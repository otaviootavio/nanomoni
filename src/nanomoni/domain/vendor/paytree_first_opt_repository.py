"""PayTree first-opt node store repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class PaytreeFirstOptNodeRepository(ABC):
    """Repository for first-opt sparse node store (Eytzinger key -> hash_b64) per channel."""

    @abstractmethod
    async def get_nodes(self, channel_id: str, node_keys: list[str]) -> dict[str, str]:
        """Return hash_b64 for the given node keys in one round-trip (MGET). Missing keys omitted."""
        pass

    @abstractmethod
    async def get_channel_and_nodes(
        self,
        channel_id: str,
        read_keys: list[str],
    ) -> tuple[Optional[str], dict[str, str]]:
        """One DB shot: GET channel + MGET nodes. Returns (channel_json, {k: v})."""
        pass

    @abstractmethod
    async def get_nodes_and_merge(
        self,
        channel_id: str,
        read_keys: list[str],
        updates: dict[str, str],
    ) -> dict[str, str]:
        """One DB shot: MGET read_keys, then MSET+ZADD for updates; return read key -> value (empty string if missing)."""
        pass

    @abstractmethod
    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None:
        """Merge updates (node_key -> hash_b64) into the store; create store if missing (one DB shot when using script)."""
        pass

    @abstractmethod
    async def save_nodes_and_save_payment_channel(
        self,
        channel_id: str,
        node_updates: dict[str, str],
        channel_json: str,
        is_closed: bool,
        created_at_ts: float,
    ) -> None:
        """One DB shot: merge_nodes(node_updates) + payment channel SET + open/closed set updates."""
        pass

    @abstractmethod
    async def delete(self, channel_id: str) -> int:
        """Remove all first-opt data for the channel. Returns number of keys deleted."""
        pass
