"""PayTree: Merkle tree-based cumulative micropayment proofs."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Final, Optional

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


def _cache_key(level: int, position: int) -> str:
    """Canonical cache key for Merkle nodes."""
    return f"{level}:{position}"


def compute_tree_depth(max_i: int) -> int:
    """Return tree depth (number of sibling levels) for indices [0..max_i]."""
    if max_i < 0:
        raise ValueError("max_i must be >= 0")
    leaf_count = max_i + 1
    padded = 1 if leaf_count <= 1 else 1 << (leaf_count - 1).bit_length()
    return padded.bit_length() - 1


def compute_lcp(a: int, b: int, n: int) -> int:
    """Longest common prefix length for n-bit integers."""
    if a < 0 or b < 0:
        raise ValueError("indices must be >= 0")
    if n < 0:
        raise ValueError("n must be >= 0")
    xor = a ^ b
    if xor == 0:
        return n
    return max(0, n - xor.bit_length())


def update_cache_with_siblings_and_path(
    *,
    i: int,
    leaf_b64: str,
    full_siblings_b64: list[str],
    node_cache_b64: dict[str, str],
) -> Optional[dict[str, str]]:
    """Store both P(x) siblings and Q(x) computed path nodes.

    Mutates *node_cache_b64* in place and returns it (or ``None`` on
    decode error).
    """
    try:
        current = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in full_siblings_b64]
    except Exception:
        return None

    node_cache_b64[_cache_key(0, i)] = leaf_b64

    current_position = i
    for level, sibling_bytes in enumerate(siblings):
        sibling_pos = current_position ^ 1
        node_cache_b64[_cache_key(level, sibling_pos)] = bytes_to_b64(sibling_bytes)

        if (current_position % 2) == 0:
            parent = hash_bytes(current + sibling_bytes)
        else:
            parent = hash_bytes(sibling_bytes + current)

        current = parent
        current_position = current_position // 2
        node_cache_b64[_cache_key(level + 1, current_position)] = bytes_to_b64(current)

    return node_cache_b64


def verify_proof_to_known_node(
    *,
    leaf_hash: bytes,
    leaf_index: int,
    siblings: list[bytes],
    known_node_hash: bytes,
    known_node_level: int,
) -> bool:
    """
    Verify a Merkle proof segment from leaf up to a known node.

    `siblings` must contain exactly one sibling per level in [0, known_node_level).
    """
    if leaf_index < 0 or known_node_level < 0:
        return False
    if len(siblings) != known_node_level:
        return False

    current = leaf_hash
    current_index = leaf_index
    for sibling in siblings:
        is_left = (current_index % 2) == 0
        if is_left:
            current = hash_bytes(current + sibling)
        else:
            current = hash_bytes(sibling + current)
        current_index = current_index // 2
    return current == known_node_hash


def _next_power_of_two(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    if n <= 0:
        return 1
    if n & (n - 1) == 0:
        return n
    return 1 << (n.bit_length())


def _build_merkle_tree(leaves: list[bytes]) -> tuple[bytes, list[list[bytes]]]:
    """
    Build a binary Merkle tree from a list of leaf hashes.

    Args:
        leaves: List of leaf hashes (bytes)

    Returns:
        (root_hash, tree_levels) where tree_levels[0] is the leaves,
        tree_levels[1] is the next level up, etc., and tree_levels[-1] contains only the root.
    """
    if not leaves:
        raise ValueError("Cannot build Merkle tree with empty leaves")

    # Pad to next power of 2 by duplicating the last leaf
    padded_size = _next_power_of_two(len(leaves))
    padded_leaves = leaves + [leaves[-1]] * (padded_size - len(leaves))

    tree_levels: list[list[bytes]] = [padded_leaves]

    current_level = padded_leaves
    while len(current_level) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = (
                current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
            )
            parent = hash_bytes(left + right)
            next_level.append(parent)
        tree_levels.append(next_level)
        current_level = next_level

    root = tree_levels[-1][0]
    return root, tree_levels


def _get_merkle_proof(
    tree_levels: list[list[bytes]], leaf_index: int
) -> tuple[bytes, list[bytes]]:
    """
    Get Merkle proof (leaf hash + siblings) for a given leaf index.

    Args:
        tree_levels: Tree structure from _build_merkle_tree
        leaf_index: Index of the leaf (0-based)

    Returns:
        (leaf_hash, siblings_list) where siblings_list contains sibling hashes
        from leaf level up to root (excluding root itself).
    """
    if not tree_levels:
        raise ValueError("Empty tree levels")
    if leaf_index < 0 or leaf_index >= len(tree_levels[0]):
        raise ValueError(
            f"Leaf index {leaf_index} out of range [0, {len(tree_levels[0])})"
        )

    leaf_hash = tree_levels[0][leaf_index]
    siblings: list[bytes] = []

    current_index = leaf_index
    for level_idx in range(len(tree_levels) - 1):
        current_level = tree_levels[level_idx]
        # Determine if current_index is left (even) or right (odd)
        is_left = (current_index % 2) == 0
        sibling_index = current_index + 1 if is_left else current_index - 1
        if sibling_index < len(current_level):
            siblings.append(current_level[sibling_index])
        else:
            # If no sibling exists (odd number of nodes), duplicate the current node
            siblings.append(current_level[current_index])
        current_index = current_index // 2

    return leaf_hash, siblings


def _verify_merkle_proof(
    leaf_hash: bytes, siblings: list[bytes], root: bytes, leaf_index: int
) -> bool:
    """
    Verify a Merkle proof against a root.

    Args:
        leaf_hash: Hash of the leaf being proven
        siblings: List of sibling hashes from leaf to root
        root: Expected root hash
        leaf_index: Index of the leaf (0-based)

    Returns:
        True if the proof is valid, False otherwise
    """
    return verify_proof_to_known_node(
        leaf_hash=leaf_hash,
        leaf_index=leaf_index,
        siblings=siblings,
        known_node_hash=root,
        known_node_level=len(siblings),
    )


@dataclass(frozen=True)
class Paytree:
    """
    Client-side PayTree helper.

    This object is responsible for:
    - Generating the PayTree commitment root (base64)
    - Generating per-payment proofs (i, leaf_b64, siblings_b64[]) for a chosen index i

    The tree is built from max_i + 1 leaves (indices 0 to max_i).
    Each leaf is a hash of a random secret: leaf_i = H(secret_i).
    """

    max_i: int
    commitment_root_b64: str
    _tree_levels: list[list[bytes]]
    _leaf_secrets: list[bytes]

    @staticmethod
    def create(*, max_i: int, seed: Optional[bytes] = None) -> "Paytree":
        """
        Create a PayTree with max_i + 1 leaves (indices 0 to max_i).

        Args:
            max_i: Maximum index (inclusive). Tree will have max_i + 1 leaves.
            seed: Optional seed for deterministic generation (for testing).
                  If None, uses random secrets for each leaf.

        Returns:
            Paytree instance with commitment root and tree structure.
        """
        if max_i < 0:
            raise ValueError("max_i must be >= 0")

        # Generate random secrets for each leaf
        if seed is not None:
            # For deterministic testing: derive secrets from seed

            leaf_secrets: list[bytes] = []
            for i in range(max_i + 1):
                h = hashlib.sha256()
                h.update(seed)
                h.update(i.to_bytes(8, "big"))
                leaf_secrets.append(h.digest())
        else:
            leaf_secrets = [os.urandom(32) for _ in range(max_i + 1)]

        # Hash each secret to get leaf hashes
        leaves = [hash_bytes(secret) for secret in leaf_secrets]

        # Build Merkle tree
        root, tree_levels = _build_merkle_tree(leaves)
        root_b64 = bytes_to_b64(root)

        return Paytree(
            max_i=max_i,
            commitment_root_b64=root_b64,
            _tree_levels=tree_levels,
            _leaf_secrets=leaf_secrets,
        )

    def payment_proof(self, *, i: int) -> tuple[int, str, list[str]]:
        """
        Generate a payment proof for index i.

        Args:
            i: Leaf index (0 <= i <= max_i)

        Returns:
            (i, leaf_b64, siblings_b64[]) where:
            - i: the index
            - leaf_b64: base64-encoded leaf hash
            - siblings_b64: list of base64-encoded sibling hashes
        """
        if i < 0 or i > self.max_i:
            raise ValueError(f"Index i={i} out of range [0, {self.max_i}]")

        leaf_hash, siblings = _get_merkle_proof(self._tree_levels, i)
        leaf_b64 = bytes_to_b64(leaf_hash)
        siblings_b64 = [bytes_to_b64(s) for s in siblings]

        return i, leaf_b64, siblings_b64


def compute_cumulative_owed_amount(*, i: int, unit_value: int) -> int:
    """Compute owed amount from the PayTree index i and unit value."""
    if i < 0:
        raise ValueError("i must be >= 0")
    if unit_value <= 0:
        raise ValueError("unit_value must be > 0")
    return i * unit_value


def verify_paytree_proof(
    *,
    i: int,
    leaf_b64: str,
    siblings_b64: list[str],
    root_b64: str,
) -> bool:
    """
    Verify a PayTree proof against a commitment root.

    Args:
        i: Leaf index (0-based)
        leaf_b64: Base64-encoded leaf hash
        siblings_b64: List of base64-encoded sibling hashes
        root_b64: Base64-encoded commitment root

    Returns:
        True if the proof is valid, False otherwise
    """
    try:
        leaf_hash = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in siblings_b64]
        root = b64_to_bytes(root_b64)
    except Exception:
        return False

    return _verify_merkle_proof(leaf_hash, siblings, root, i)
