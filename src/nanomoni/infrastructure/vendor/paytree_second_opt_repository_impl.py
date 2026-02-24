"""PayTree Second Opt repository implementation."""

from __future__ import annotations

from typing import Optional

from ...crypto.merkle_index import (
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
    key,
)
from ...domain.vendor.entities import (
    PaytreeSecondOptPaymentChannel,
    PaytreeSecondOptState,
)
from ...domain.vendor.paytree_second_opt_repository import PaytreeSecondOptRepository
from .payment_channel_repository_base_impl import PaymentChannelRepositoryBaseImpl


def _paytree_second_opt_hash_key(channel_id: str) -> str:
    return f"paytree2opt_nodes:{channel_id}"


class PaytreeSecondOptRepositoryImpl(
    PaymentChannelRepositoryBaseImpl, PaytreeSecondOptRepository
):
    """KeyValueStore implementation for PayTree Second Opt payment channels."""

    async def get_paytree_second_opt_state(
        self, channel_id: str
    ) -> Optional[PaytreeSecondOptState]:
        key_name = f"paytree_second_opt_state:latest:{channel_id}"
        raw = await self.store.get(key_name)
        if not raw:
            return None
        return PaytreeSecondOptState.model_validate_json(raw)

    async def get_paytree_second_opt_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[
        Optional[PaytreeSecondOptPaymentChannel], Optional[PaytreeSecondOptState]
    ]:
        channel_key = f"payment_channel:{channel_id}"
        state_key = f"paytree_second_opt_state:latest:{channel_id}"
        channel_json, state_json = await self.store.mget([channel_key, state_key])
        if not channel_json:
            return None, None
        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise TypeError("Payment channel is not PayTree Second Opt-enabled")
        state = (
            PaytreeSecondOptState.model_validate_json(state_json)
            if state_json
            else None
        )
        return channel, state

    async def get_paytree_second_opt_channel_state_and_sibling_cache(
        self, *, channel_id: str, i: int, max_i: int
    ) -> tuple[
        Optional[PaytreeSecondOptPaymentChannel],
        Optional[PaytreeSecondOptState],
        dict[str, str],
    ]:
        depth = compute_tree_depth(max_i)
        sibling_fields = [
            key(level, get_sibling_position_at_level(i, level))
            for level in range(depth)
        ]
        path_fields = [
            key(level, get_ancestor_at_level(i, level)) for level in range(depth)
        ]
        fields = sibling_fields + path_fields

        channel_key = f"payment_channel:{channel_id}"
        state_key = f"paytree_second_opt_state:latest:{channel_id}"
        hash_key = _paytree_second_opt_hash_key(channel_id)

        mget_results, hash_values = await self.store.mget_and_hmget(
            mget_keys=[channel_key, state_key],
            hmget_key=hash_key,
            hmget_fields=fields,
        )
        channel_json = mget_results[0] if mget_results else None
        state_json = mget_results[1] if len(mget_results) > 1 else None

        if not channel_json:
            return None, None, {}

        channel = self._deserialize_channel(channel_json)
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise TypeError("Payment channel is not PayTree Second Opt-enabled")
        state = (
            PaytreeSecondOptState.model_validate_json(state_json)
            if state_json
            else None
        )
        cache: dict[str, str] = {}
        for field, value in zip(fields, hash_values):
            if value is not None:
                cache[field] = value
        return channel, state, cache

    async def save_paytree_second_opt_payment(
        self,
        channel: PaytreeSecondOptPaymentChannel,
        new_state: PaytreeSecondOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        if channel.channel_id != new_state.channel_id:
            raise ValueError(
                "Channel channel_id mismatch for PayTree Second Opt payment"
            )

        latest_key = f"paytree_second_opt_state:latest:{new_state.channel_id}"
        channel_key = f"payment_channel:{new_state.channel_id}"
        hash_key = _paytree_second_opt_hash_key(new_state.channel_id)
        payload_json = new_state.model_dump_json()
        node_args = [f for pair in node_entries.items() for f in pair]

        result = await self.store.run_script(
            "save_paytree_second_opt_payment",
            keys=[latest_key, channel_key, hash_key],
            args=[payload_json, str(new_state.i)] + node_args,
        )

        code = (
            int(result[0])
            if result and result[0] is not None and result[0] != ""
            else 0
        )
        payload = (
            result[1] if len(result) > 1 and result[1] and result[1] != "" else None
        )

        if code == 1:
            if payload is None:
                raise RuntimeError(
                    "Unexpected: save_paytree_second_opt_payment returned success but no payload"
                )
            return 1, PaytreeSecondOptState.model_validate_json(payload)
        elif code == 0:
            return (
                0,
                PaytreeSecondOptState.model_validate_json(payload) if payload else None,
            )
        elif code == 3:
            return (
                3,
                PaytreeSecondOptState.model_validate_json(payload) if payload else None,
            )
        else:
            return 2, None

    async def save_channel_and_initial_paytree_second_opt_state(
        self,
        channel: PaytreeSecondOptPaymentChannel,
        initial_state: PaytreeSecondOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        channel_key = f"payment_channel:{channel.channel_id}"
        latest_key = f"paytree_second_opt_state:latest:{channel.channel_id}"
        hash_key = _paytree_second_opt_hash_key(channel.channel_id)

        channel_json = channel.model_dump_json()
        state_json = initial_state.model_dump_json()
        created_ts = channel.created_at.timestamp()
        node_args = [f for pair in node_entries.items() for f in pair]

        result = await self.store.run_script(
            "save_channel_and_initial_paytree_second_opt_state",
            keys=[channel_key, latest_key, hash_key],
            args=[channel_json, state_json, str(created_ts), channel.channel_id]
            + node_args,
        )
        code = int(result[0])
        if code == 1:
            return 1, initial_state
        return 0, None

    async def get_paytree_second_opt_sibling_cache_for_index(
        self,
        *,
        channel_id: str,
        i: int,
        max_i: int,
        trusted_level: Optional[int] = None,
    ) -> dict[str, str]:
        depth = compute_tree_depth(max_i)
        sibling_depth = depth
        if trusted_level is not None:
            sibling_depth = min(depth, max(0, trusted_level))

        sibling_fields = [
            key(level, get_sibling_position_at_level(i, level))
            for level in range(sibling_depth)
        ]
        include_trusted_q_node = sibling_depth < depth
        if include_trusted_q_node:
            sibling_fields.append(
                key(sibling_depth, get_ancestor_at_level(i, sibling_depth))
            )

        hash_key = _paytree_second_opt_hash_key(channel_id)
        values = await self.store.hmget(hash_key, sibling_fields)
        cache: dict[str, str] = {}
        for field, value in zip(sibling_fields, values):
            if value is not None:
                cache[field] = value
        return cache

    async def get_paytree_second_opt_siblings_for_settlement(
        self, *, channel_id: str, i: int, max_i: int
    ) -> list[str]:
        depth = compute_tree_depth(max_i)
        fields = [
            key(level, get_sibling_position_at_level(i, level))
            for level in range(depth)
        ]
        hash_key = _paytree_second_opt_hash_key(channel_id)
        values = await self.store.hmget(hash_key, fields)
        siblings: list[str] = []
        for value in values:
            if value is None:
                raise ValueError(
                    "Missing required sibling in node cache for settlement"
                )
            siblings.append(value)
        return siblings
