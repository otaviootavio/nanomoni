"""In-memory implementation of KeyValueStore for testing."""

from __future__ import annotations

import json
from typing import Any, List, Mapping, Optional

from nanomoni.infrastructure.storage import KeyValueStore


class InMemoryKeyValueStore(KeyValueStore):
    """In-memory implementation of KeyValueStore for fast testing."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._sorted_sets: dict[str, list[tuple[str, float]]] = {}
        self._script_cache: dict[str, str] = {}
        self._script_sources: dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        return [self._data.get(key) for key in keys]

    async def set(self, key: str, value: str) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def zadd(self, key: str, mapping: Mapping[str, float]) -> int:
        """Add members to sorted set."""
        if key not in self._sorted_sets:
            self._sorted_sets[key] = []

        added = 0
        for member, score in mapping.items():
            # Check if member already exists
            member_exists = any(m == member for m, _ in self._sorted_sets[key])
            # Remove existing member if present
            self._sorted_sets[key] = [
                (m, s) for m, s in self._sorted_sets[key] if m != member
            ]
            # Add new member
            self._sorted_sets[key].append((member, score))
            # Only count as added if it was a new member
            if not member_exists:
                added += 1
            # Keep sorted by score (descending)
            self._sorted_sets[key].sort(key=lambda x: x[1], reverse=True)

        return added

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        """Get range from sorted set (already sorted descending)."""
        if key not in self._sorted_sets:
            return []
        members = [m for m, _ in self._sorted_sets[key]]
        # Redis zrevrange is inclusive on both ends
        # Handle end=-1 as end of list (include all remaining members)
        if end == -1:
            slice_end = None
        else:
            slice_end = end + 1
        return members[start:slice_end]

    async def zrem(self, key: str, member: str) -> int:
        """Remove member from sorted set."""
        if key not in self._sorted_sets:
            return 0
        original_len = len(self._sorted_sets[key])
        self._sorted_sets[key] = [
            (m, s) for m, s in self._sorted_sets[key] if m != member
        ]
        return 1 if len(self._sorted_sets[key]) < original_len else 0

    async def eval(self, script: str, keys: List[str], args: List[str]) -> Any:
        """Execute a Lua script (simplified Python implementation)."""
        # For testing, we'll implement the specific scripts we use
        # This is a simplified evaluator that handles our specific scripts
        return await self._execute_script_logic(script, keys, args, script_name=None)

    async def register_script(self, name: str, script: str) -> str:
        """Register a script (return mock SHA1)."""
        self._script_cache[name] = f"sha1_{name}"
        self._script_sources[name] = script
        return f"sha1_{name}"

    async def run_script(self, name: str, keys: List[str], args: List[str]) -> Any:
        """Execute script by name."""
        if name not in self._script_cache:
            raise ValueError(f"Script '{name}' not registered")
        script = self._script_sources[name]
        return await self._execute_script_logic(script, keys, args, script_name=name)

    async def _execute_script_logic(
        self,
        script: str,
        keys: List[str],
        args: List[str],
        script_name: str | None = None,
    ) -> Any:
        """Execute script logic in Python (simplified for our specific scripts)."""
        # This is a simplified interpreter for the specific Lua scripts we use
        # We'll implement the logic directly in Python

        # Helper to check if key exists
        def key_exists(key: str) -> int:
            return 1 if key in self._data else 0

        # Helper to get value
        def get_value(key: str) -> Optional[str]:
            return self._data.get(key)

        # Helper to set value
        def set_value(key: str, value: str) -> None:
            self._data[key] = value

        # Helper for ZADD
        def zadd(key: str, score: float, member: str) -> None:
            if key not in self._sorted_sets:
                self._sorted_sets[key] = []
            # Remove existing
            self._sorted_sets[key] = [
                (m, s) for m, s in self._sorted_sets[key] if m != member
            ]
            self._sorted_sets[key].append((member, score))
            self._sorted_sets[key].sort(key=lambda x: x[1], reverse=True)

        # Determine script type and execute based on script content or name
        script_lower = script.lower()
        script_name_lower = (script_name or "").lower()

        # Check by script name first (more reliable)
        if script_name_lower == "save_signature_payment" or (
            "save_signature_payment" in script_lower
            and ("new_amount" in script_lower or "channel_amount" in script_lower)
        ):
            return self._execute_save_signature_payment(keys, args)
        elif script_name_lower == "save_payword_payment" or (
            "save_payword_payment" in script_lower and "new_k" in script_lower
        ):
            return self._execute_save_payword_payment(keys, args)
        elif script_name_lower == "save_paytree_payment" or (
            "save_paytree_payment" in script_lower and "new_i" in script_lower
        ):
            return self._execute_save_paytree_payment(keys, args)
        elif (
            "save_channel_and_initial" in script_lower or "channel_json" in script_lower
        ):
            return self._execute_save_channel_and_initial_state(keys, args)
        elif "create_channel" in script_lower or (
            "exists" in script_lower and "set" in script_lower and len(keys) == 1
        ):
            return self._execute_create_channel(keys, args)
        else:
            # Generic fallback - try to parse basic operations
            raise NotImplementedError(
                f"Script not implemented. Script preview: {script[:200]}"
            )

    def _execute_save_signature_payment(
        self, keys: List[str], args: List[str]
    ) -> list[Any]:
        """Execute save_signature_payment script logic."""
        latest_key = keys[0]
        channel_key = keys[1]
        new_val = args[0]
        new_amount = float(args[1])
        channel_amount = float(args[2])

        # Check channel existence
        if channel_key not in self._data:
            return [2, ""]

        # Check capacity
        if new_amount > channel_amount:
            error_current = self._data.get(latest_key, "") or ""
            return [3, error_current]

        # Get current state
        current_raw: Optional[str] = self._data.get(latest_key)
        if not current_raw:
            self._data[latest_key] = new_val
            return [1, new_val]

        # Parse current state
        current = json.loads(current_raw)
        current_amount = float(current.get("cumulative_owed_amount", 0))

        if new_amount > current_amount:
            self._data[latest_key] = new_val
            return [1, new_val]
        else:
            return [0, current_raw]

    def _execute_save_payword_payment(
        self, keys: List[str], args: List[str]
    ) -> list[Any]:
        """Execute save_payword_payment script logic."""
        latest_key = keys[0]
        channel_key = keys[1]
        new_val = args[0]
        new_k = float(args[1])

        # Get channel
        channel_raw: Optional[str] = self._data.get(channel_key)
        if not channel_raw:
            return [2, ""]

        channel = json.loads(channel_raw)
        max_k = float(channel.get("payword_max_k", channel.get("max_k", 0)))
        if not max_k:
            return [2, ""]

        if new_k > max_k:
            error_current = self._data.get(latest_key, "") or ""
            return [3, error_current]

        current_raw: Optional[str] = self._data.get(latest_key)
        if not current_raw:
            self._data[latest_key] = new_val
            return [1, new_val]

        current = json.loads(current_raw)
        current_k = float(current.get("k", 0))

        if new_k > current_k:
            self._data[latest_key] = new_val
            return [1, new_val]
        else:
            return [0, current_raw]

    def _execute_save_paytree_payment(
        self, keys: List[str], args: List[str]
    ) -> list[Any]:
        """Execute save_paytree_payment script logic."""
        latest_key = keys[0]
        channel_key = keys[1]
        new_val = args[0]
        new_i = float(args[1])

        # Get channel
        channel_raw: Optional[str] = self._data.get(channel_key)
        if not channel_raw:
            return [2, ""]

        channel = json.loads(channel_raw)
        max_i = float(channel.get("paytree_max_i", 0))
        if not max_i:
            return [2, ""]

        if new_i > max_i:
            error_current = self._data.get(latest_key, "") or ""
            return [3, error_current]

        current_raw: Optional[str] = self._data.get(latest_key)
        if not current_raw:
            self._data[latest_key] = new_val
            return [1, new_val]

        current = json.loads(current_raw)
        current_i = float(current.get("i", 0))

        if new_i > current_i:
            self._data[latest_key] = new_val
            return [1, new_val]
        else:
            return [0, current_raw]

    def _execute_save_channel_and_initial_state(
        self, keys: List[str], args: List[str]
    ) -> list[Any]:
        """Execute save_channel_and_initial_state script logic."""
        channel_key = keys[0]
        latest_key = keys[1]
        channel_json = args[0]
        state_json = args[1]
        created_ts = float(args[2])
        channel_id = args[3]

        # Check if channel exists
        if channel_key in self._data:
            return [0, ""]

        # Check if state exists
        if latest_key in self._data:
            return [0, ""]

        # Save channel
        self._data[channel_key] = channel_json

        # Save state
        self._data[latest_key] = state_json

        # Update indices
        self._sorted_sets.setdefault("payment_channels:all", []).append(
            (channel_id, created_ts)
        )
        self._sorted_sets.setdefault("payment_channels:open", []).append(
            (channel_id, created_ts)
        )
        # Keep sorted
        self._sorted_sets["payment_channels:all"].sort(key=lambda x: x[1], reverse=True)
        self._sorted_sets["payment_channels:open"].sort(
            key=lambda x: x[1], reverse=True
        )

        return [1, state_json]

    def _execute_create_channel(self, keys: List[str], args: List[str]) -> list[Any]:
        """Execute create_channel script logic."""
        channel_key = keys[0]
        channel_json = args[0]

        if channel_key in self._data:
            return [0, ""]

        self._data[channel_key] = channel_json
        return [1, channel_json]

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self._data.clear()
        self._sorted_sets.clear()
        self._script_cache.clear()
        self._script_sources.clear()
