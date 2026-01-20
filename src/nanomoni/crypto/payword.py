from __future__ import annotations

import base64
import bisect
import hashlib
from dataclasses import dataclass
from typing import Optional
from typing import Final


SHA256: Final[str] = "sha256"


def b64_to_bytes(data_b64: str) -> bytes:
    """Decode a base64 string into raw bytes (strict validation)."""
    return base64.b64decode(data_b64, validate=True)


def bytes_to_b64(data: bytes) -> str:
    """Encode raw bytes into base64 string."""
    return base64.b64encode(data).decode("utf-8")


def hash_bytes(data: bytes) -> bytes:
    """Hash bytes (fixed algorithm: SHA-256)."""
    return hashlib.new(SHA256, data).digest()


def hash_n(data: bytes, n: int) -> bytes:
    """Apply hash n times (n >= 0)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    out = data
    for _ in range(n):
        out = hash_bytes(out)
    return out


def build_hash_chain(seed: bytes, n: int) -> list[bytes]:
    """
    Build a hash chain [w0, w1, ..., wn] where:
      w0 = seed
      wi = H(w(i-1)) for i in 1..n

    Returns a list of length (n + 1).
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    chain: list[bytes] = [seed]
    cur = seed
    for _ in range(n):
        cur = hash_bytes(cur)
        chain.append(cur)
    return chain


def _collect_midpoint_pebbles(*, n: int, pebble_count: int) -> list[int]:
    """
    Return up to `pebble_count` pebble indices using recursive midpoint splitting.

    Traversal is **depth-first / preorder**: append `mid = (lo + hi) // 2`, then recurse
    left (`rec(lo, mid)`) and then right (`rec(mid, hi)`). Because we stop once we have
    enough pebbles, the returned order reflects that DFS traversal, not a breadth-first
    (level-order) walk of the implicit midpoint tree.

    Note: callers that want monotonically increasing indices can sort the result (see
    `PaywordPebbleCache.build`).

    Examples (n=100):
      pebble_count=0 -> []
      pebble_count=1 -> [50]
      pebble_count=3 -> [50, 25, 12]
      pebble_count=7 -> [50, 25, 12, 6, 3, 1, 2]
    """
    if pebble_count < 0:
        raise ValueError("pebble_count must be >= 0")
    if pebble_count == 0:
        return []
    if n <= 1:
        return []

    out: list[int] = []

    def rec(lo: int, hi: int) -> None:
        if len(out) >= pebble_count:
            return
        mid = (lo + hi) // 2
        if mid == lo or mid == hi:
            return
        out.append(mid)
        rec(lo, mid)
        rec(mid, hi)

    rec(0, n)
    # Ensure uniqueness and stable order (rec can theoretically repeat mids on tiny ranges).
    seen: set[int] = set()
    unique: list[int] = []
    for idx in out:
        if 0 < idx < n and idx not in seen:
            seen.add(idx)
            unique.append(idx)
        if len(unique) >= pebble_count:
            break
    return unique


@dataclass(frozen=True)
class PaywordPebbleCache:
    """
    Client-side helper for PayWord token generation with a memory/CPU tradeoff.

    We keep only `pebble_count` checkpoints ("pebbles") plus the seed (index 0).
    To get token for counter k, we compute:
      idx = max_k - k
      token = w_idx  where w_i = H^i(seed)
    by starting from the nearest pebble at index j <= idx and hashing forward (idx-j) times.

    This matches the intuition you described: more pebbles => shorter gaps => fewer hashes.
    """

    max_k: int
    root_b64: str
    pebble_indices: list[int]
    _values: dict[int, bytes]

    @staticmethod
    def build(*, seed: bytes, max_k: int, pebble_count: int) -> "PaywordPebbleCache":
        if max_k <= 0:
            raise ValueError("max_k must be > 0")
        if pebble_count < 0:
            raise ValueError("pebble_count must be >= 0")

        pebble_indices = sorted(
            _collect_midpoint_pebbles(n=max_k, pebble_count=pebble_count)
        )
        wanted: set[int] = set(pebble_indices)

        values: dict[int, bytes] = {0: seed}
        cur = seed
        for i in range(1, max_k + 1):
            cur = hash_bytes(cur)
            if i in wanted:
                values[i] = cur

        root_b64 = bytes_to_b64(cur)  # i == max_k
        return PaywordPebbleCache(
            max_k=max_k,
            root_b64=root_b64,
            pebble_indices=pebble_indices,
            _values=values,
        )

    def payment_proof_b64(self, *, k: int) -> str:
        if k < 0 or k > self.max_k:
            raise ValueError("k out of bounds")
        idx = self.max_k - k

        # Choose the nearest stored checkpoint j <= idx (always have 0).
        # NOTE: avoid rebuilding a large candidates list on every call.
        pos = bisect.bisect_right(self.pebble_indices, idx)
        j = self.pebble_indices[pos - 1] if pos > 0 else 0

        start = self._values.get(j)
        if start is None:
            # Should not happen: all pebble indices are filled during build().
            raise RuntimeError(f"Missing pebble value at index {j}")

        token = hash_n(start, idx - j)
        return bytes_to_b64(token)


@dataclass(frozen=True)
class Payword:
    """
    Client-side PayWord helper.

    This object is responsible for:
    - Generating the PayWord commitment root (base64)
    - Generating per-payment proofs (base64) for a chosen counter k

    Internally, it uses a pebbling cache to trade memory for hashing work.
    """

    max_k: int
    commitment_root_b64: str
    _cache: PaywordPebbleCache

    @staticmethod
    def create(
        *, max_k: int, pebble_count: int, seed: Optional[bytes] = None
    ) -> "Payword":
        if seed is None:
            # Local import to avoid pulling os into library paths that don't need it.
            import os

            seed = os.urandom(32)
        cache = PaywordPebbleCache.build(
            seed=seed, max_k=max_k, pebble_count=pebble_count
        )
        return Payword(max_k=max_k, commitment_root_b64=cache.root_b64, _cache=cache)

    def payment_proof_b64(self, *, k: int) -> str:
        return self._cache.payment_proof_b64(k=k)


def compute_cumulative_owed_amount(*, k: int, unit_value: int) -> int:
    """Compute owed amount from the PayWord counter k and unit value."""
    if k < 0:
        raise ValueError("k must be >= 0")
    if unit_value <= 0:
        raise ValueError("unit_value must be > 0")
    return k * unit_value


def verify_token_against_root(
    *,
    token: bytes,
    k: int,
    root: bytes,
) -> bool:
    """Verify that H^k(token) == root."""
    return hash_n(token, k) == root


def verify_token_incremental(
    *,
    token: bytes,
    prev_token: bytes,
    delta_k: int,
) -> bool:
    """Verify that H^(delta_k)(token) == prev_token."""
    return hash_n(token, delta_k) == prev_token
