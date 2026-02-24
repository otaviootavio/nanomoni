"""Redis-backed implementation of VerifierNodeRepository."""

from __future__ import annotations

import json

from ...domain.vendor.verifier_node_repository import VerifierNodeRepository
from ..storage import KeyValueStore


def _key(tree_id: str) -> str:
    return f"verifier_nodes:{tree_id}"


class VerifierNodeRepositoryImpl(VerifierNodeRepository):
    """KeyValueStore implementation for verifier node persistence."""

    def __init__(self, store: KeyValueStore) -> None:
        self.store = store

    async def get_nodes(self, tree_id: str) -> dict[str, str]:
        raw = await self.store.get(_key(tree_id))
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    async def save_nodes(self, tree_id: str, nodes: dict[str, str]) -> None:
        payload = json.dumps(nodes)
        await self.store.set(_key(tree_id), payload)
