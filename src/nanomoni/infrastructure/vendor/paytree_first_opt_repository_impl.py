"""PayTree first-opt node store repository implementation (Redis per-node keys + index)."""

from __future__ import annotations

from ...domain.vendor.paytree_first_opt_repository import PaytreeFirstOptNodeRepository
from ...infrastructure.storage import KeyValueStore


def _node_key(channel_id: str, node_key: str) -> str:
    return f"paytree_first_opt_node:{channel_id}:{node_key}"


def _index_key(channel_id: str) -> str:
    return f"paytree_first_opt_index:{channel_id}"


class PaytreeFirstOptNodeRepositoryImpl(PaytreeFirstOptNodeRepository):
    """KeyValueStore implementation for first-opt sparse node store per channel."""

    def __init__(self, store: KeyValueStore) -> None:
        self._store = store

    async def get_channel_and_nodes(
        self,
        channel_id: str,
        read_keys: list[str],
    ) -> tuple[str | None, dict[str, str]]:
        """One DB shot: MGET channel + 2 node keys (read-only)."""
        channel_key = f"payment_channel:{channel_id}"
        read_redis_keys = [_node_key(channel_id, k) for k in read_keys]
        if len(read_redis_keys) < 2:
            read_redis_keys.extend([read_redis_keys[0]] * (2 - len(read_redis_keys)))
        keys = [channel_key, read_redis_keys[0], read_redis_keys[1]]
        values = await self._store.mget(keys)
        channel_raw = (values[0] or "").strip() if values and len(values) > 0 else ""
        channel_json = channel_raw if channel_raw else None
        out: dict[str, str] = {}
        for i, k in enumerate(read_keys[:2]):
            val = (
                (values[i + 1] or "").strip() if values and i + 1 < len(values) else ""
            )
            out[k] = val
        return channel_json, out

    async def get_nodes(self, channel_id: str, node_keys: list[str]) -> dict[str, str]:
        """Fetch multiple node keys in one round-trip (MGET)."""
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
        """One DB shot: MGET read_keys, MSET+ZADD updates; return read key -> value ('' if missing)."""
        index = _index_key(channel_id)
        read_redis_keys = [_node_key(channel_id, k) for k in read_keys]
        # Script expects exactly 2 read keys; pad if needed
        if len(read_redis_keys) < 2:
            read_redis_keys.extend([read_redis_keys[0]] * (2 - len(read_redis_keys)))
        keys = [index, read_redis_keys[0], read_redis_keys[1]]
        args = [channel_id, str(len(updates))]
        for node_key, hash_b64 in updates.items():
            args.extend([node_key, hash_b64])
        result = await self._store.run_script(
            "paytree_first_opt_get_nodes_and_merge", keys=keys, args=args
        )
        # result = [read1 or '', read2 or '']
        out: dict[str, str] = {}
        for i, k in enumerate(read_keys[:2]):
            out[k] = (result[i] or "") if result and i < len(result) else ""
        return out

    async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None:
        """One DB shot: MSET + ZADD via Lua script."""
        if not updates:
            return
        index = _index_key(channel_id)
        keys = [index]
        args = [channel_id, str(len(updates))]
        for node_key, hash_b64 in updates.items():
            args.extend([node_key, hash_b64])
        await self._store.run_script(
            "paytree_first_opt_merge_nodes", keys=keys, args=args
        )

    async def save_nodes_and_save_payment_channel(
        self,
        channel_id: str,
        node_updates: dict[str, str],
        channel_json: str,
        is_closed: bool,
        created_at_ts: float,
    ) -> None:
        """One DB shot: merge_nodes + payment channel update (SET + open/closed sets)."""
        index_key = _index_key(channel_id)
        channel_key = f"payment_channel:{channel_id}"
        keys = [
            index_key,
            channel_key,
            "payment_channels:open",
            "payment_channels:closed",
        ]
        n = len(node_updates)
        args = [channel_id, str(n)]
        for node_key, hash_b64 in node_updates.items():
            args.extend([node_key, hash_b64])
        args.extend([channel_json, "1" if is_closed else "0", str(created_at_ts)])
        await self._store.run_script(
            "paytree_first_opt_save_nodes_and_channel", keys=keys, args=args
        )

    async def delete(self, channel_id: str) -> int:
        index = _index_key(channel_id)
        node_keys = await self._store.zrevrange(index, 0, -1)
        count = 0
        for node_key in node_keys:
            await self._store.delete(_node_key(channel_id, node_key))
            count += 1
        await self._store.delete(index)
        count += 1  # index key
        return count
