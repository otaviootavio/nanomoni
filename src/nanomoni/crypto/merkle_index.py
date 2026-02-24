"""Merkle tree index library: path, siblings, and navigation by (level, position).

Eytzinger layout: tree operations use bitwise shifts and XOR only (left/right
shifts, bit toggling).

Glossary: key = "x:y" notation; index = Eytzinger layout (binary); hash = hash value.
No hashes here—only indices and keys. Use index_to_hash (tree or store) to obtain hashes.
"""

from __future__ import annotations

from typing import Optional


def key(level: int, position: int) -> str:
    """Key for a node at (level, position): the "level:position" notation."""
    return f"{level}:{position}"


def compute_tree_depth(max_i: int) -> int:
    """Return tree depth n for leaf indices [0..max_i]; tree has 2^n leaves.

    For n-bit leaf indices, the authentication path has n sibling levels (0..n-1).
    """
    if max_i < 0:
        raise ValueError("max_i must be >= 0")
    leaf_count = max_i + 1
    padded = 1 if leaf_count <= 1 else 1 << (leaf_count - 1).bit_length()
    return padded.bit_length() - 1


def compute_lcp(a: int, b: int, n: int) -> int:
    """Longest common prefix length LCP(a,b) for n-bit indices.

    k = LCP(a,b) determines |P(a) cap P(b)| = k (Property 1) and the unique
    intersection level n-k-1 for P(a2) cap Q(a1) (Property 2).
    """
    if a < 0 or b < 0:
        raise ValueError("indices must be >= 0")
    if n < 0:
        raise ValueError("n must be >= 0")
    xor = a ^ b
    if xor == 0:
        return n
    return max(0, n - xor.bit_length())


def get_ancestor_at_level(leaf_index: int, level: int) -> int:
    """Index of the ancestor at level on the path Q(a) from leaf to root.

    position = leaf_index >> level (Eytzinger index).
    """
    return leaf_index >> level


def get_sibling_position_at_level(leaf_index: int, level: int) -> int:
    """Index of the sibling at level on the authentication path P(a).

    Sibling of path node q_i is q_i XOR 1. position = (leaf_index >> level) ^ 1.
    """
    return (leaf_index >> level) ^ 1


def get_path_indexes(leaf_index: int, depth: int) -> list[tuple[int, int]]:
    """(level, index) for each node on the path Q(a) from leaf to root.

    Level 0 = leaf, level depth = root. Returns n+1 nodes for depth n.
    """
    if depth < 0:
        raise ValueError("depth must be >= 0")
    return [
        (level, get_ancestor_at_level(leaf_index, level)) for level in range(depth + 1)
    ]


def get_sibling_indexes(leaf_index: int, depth: int) -> list[tuple[int, int]]:
    """(level, index) for each sibling on the authentication path P(a).

    One per level 0..depth-1. Prover sends these; verifier computes path nodes.
    """
    if depth < 0:
        raise ValueError("depth must be >= 0")
    return [
        (level, get_sibling_position_at_level(leaf_index, level))
        for level in range(depth)
    ]


def get_path_keys(leaf_index: int, depth: int) -> list[str]:
    """Keys for path nodes Q(a); used to store/fetch hashes by (level, index)."""
    return [
        key(level, get_ancestor_at_level(leaf_index, level))
        for level in range(depth + 1)
    ]


def get_sibling_keys(leaf_index: int, depth: int) -> list[str]:
    """Keys for authentication path P(a); used to store/fetch sibling hashes."""
    return [
        key(level, get_sibling_position_at_level(leaf_index, level))
        for level in range(depth)
    ]


def compute_send_levels_first_opt(
    *,
    i: int,
    last_verified_index: Optional[int],
    depth: int,
) -> list[int]:
    """Levels to send in first compression: j in {0, .., n-k_max-1}.

    P_pruned(x) = nodes at levels j < n - k_max. Only the leaf with max LCP
    to x matters. When last_verified_index is None, send all levels.
    """
    if i < 0:
        raise ValueError("i must be >= 0")
    if depth < 0:
        raise ValueError("depth must be >= 0")
    if last_verified_index is None:
        return list(range(depth))
    k_max = compute_lcp(i, last_verified_index, depth)
    return list(range(max(0, depth - k_max)))


def compute_send_levels_second_opt(
    *,
    i: int,
    depth: int,
    known_keys: set[str],
) -> list[int]:
    """Levels to send in second compression: P(x) minus nodes already known.

    Verifier knows P(a_i) and Q(a_i) from prior verifications. P(x) cap Q(a_i)
    has exactly one element at level n-LCP(x,a_i)-1 (Property 2). Omit levels
    whose sibling key is in known_keys (from P union Q).
    """
    if i < 0:
        raise ValueError("i must be >= 0")
    if depth < 0:
        raise ValueError("depth must be >= 0")
    return [
        level
        for level in range(depth)
        if key(level, get_sibling_position_at_level(i, level)) not in known_keys
    ]


def is_left_child(position: int) -> bool:
    """True if position is left child (even index) in its level.

    left child = even; right = odd. Used in verification to order Hash(left, right)
    vs Hash(right, left).
    """
    return (position % 2) == 0


def parent_position(position: int) -> int:
    """Parent index at the next level; parent = child >> 1."""
    return position // 2
