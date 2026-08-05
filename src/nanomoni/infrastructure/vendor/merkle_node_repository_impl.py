"""MerkleNodeRepositoryImpl — Redis-backed sparse node store (merkle_node: key prefix)."""

from __future__ import annotations

from typing import Optional

from ...domain.vendor.merkle_node_repository import MerkleNodeRepository
from ...infrastructure.storage import KeyValueStore


def _node_key(channel_id: str, node_key: str) -> str:
    return f"merkle_node:{channel_id}:{node_key}"


def _index_key(channel_id: str) -> str:
    return f"merkle_node_index:{channel_id}"


def _parse_ref(value: object) -> Optional[int]:
    """Parse the CAS reference returned by a Lua script (str/bytes/int/None)."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


class MerkleNodeRepositoryImpl(MerkleNodeRepository):
    """KeyValueStore implementation for the new merkle_node: key space."""

    def __init__(self, store: KeyValueStore) -> None:
        self._store = store

    async def get_channel_and_nodes(
        self,
        channel_id: str,
        read_keys: list[str],
    ) -> tuple[str | None, dict[str, str]]:
        channel_key = f"payment_channel:{channel_id}"
        read_redis_keys = [_node_key(channel_id, k) for k in read_keys]
        if len(read_redis_keys) < 2:
            read_redis_keys.extend([read_redis_keys[0]] * (2 - len(read_redis_keys)))
        values = await self._store.mget(
            [channel_key, read_redis_keys[0], read_redis_keys[1]]
        )
        channel_raw = (values[0] or "").strip() if values else ""
        channel_json = channel_raw if channel_raw else None
        out: dict[str, str] = {}
        for i, k in enumerate(read_keys[:2]):
            val = (
                (values[i + 1] or "").strip() if values and i + 1 < len(values) else ""
            )
            out[k] = val
        return channel_json, out

    async def get_nodes(self, channel_id: str, node_keys: list[str]) -> dict[str, str]:
        if not node_keys:
            return {}
        keys = [_node_key(channel_id, k) for k in node_keys]
        values = await self._store.mget(keys)
        return {node_keys[i]: v for i, v in enumerate(values) if v is not None}

    async def get_nodes_and_merge(
        self,
        channel_id: str,
        read_keys: list[str],
        updates: dict[str, str],
    ) -> dict[str, str]:
        index = _index_key(channel_id)
        read_redis_keys = [_node_key(channel_id, k) for k in read_keys]
        if len(read_redis_keys) < 2:
            read_redis_keys.extend([read_redis_keys[0]] * (2 - len(read_redis_keys)))
        keys = [index, read_redis_keys[0], read_redis_keys[1]]
        args = [channel_id, str(len(updates))]
        for node_key, hash_b64 in updates.items():
            args.extend([node_key, hash_b64])
        result = await self._store.run_script(
            "merkle_get_nodes_and_merge", keys=keys, args=args
        )
        out: dict[str, str] = {}
        for i, k in enumerate(read_keys[:2]):
            out[k] = (result[i] or "") if result and i < len(result) else ""
        return out

    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None:
        if not updates:
            return
        index = _index_key(channel_id)
        keys = [index]
        args = [channel_id, str(len(updates))]
        for node_key, hash_b64 in updates.items():
            args.extend([node_key, hash_b64])
        await self._store.run_script("merkle_merge_nodes", keys=keys, args=args)

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
        index_key = _index_key(channel_id)
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"payment_state:{channel_id}"
        proof_key = f"crypto_proof:{channel_id}"
        keys = [
            index_key,
            channel_key,
            state_key,
            proof_key,
            "payment_channels:open",
            "payment_channels:closed",
        ]
        n = len(node_updates)
        args = [channel_id, str(n)]
        for node_key, hash_b64 in node_updates.items():
            args.extend([node_key, hash_b64])
        args.extend(
            [
                str(new_ref),
                state_json,
                proof_json,
                channel_json,
                "1" if is_closed else "0",
                str(created_at_ts),
            ]
        )
        result = await self._store.run_script(
            "save_payment_with_nodes", keys=keys, args=args
        )
        code = int(result[0]) if result and result[0] is not None else 0
        stored_ref = _parse_ref(result[1]) if result and len(result) > 1 else None
        return code, stored_ref

    async def delete(self, channel_id: str) -> int:
        index = _index_key(channel_id)
        node_keys = await self._store.zrevrange(index, 0, -1)
        count = 0
        for node_key in node_keys:
            await self._store.delete(_node_key(channel_id, node_key))
            count += 1
        await self._store.delete(index)
        return count + 1
