"""PayTree child-pair protocol: heap-indexed child revelation per payment.

Nodes are addressed by their 1-based Eytzinger index k (root = 1; children of
k are 2k and 2k+1) — the same numbering `merkle_index.eytzinger_index`
already produces for (level, position). Payment k reveals the two children of
node k; the vendor accepts iff H(left, right) == the hash it already knows
for node k, then learns nodes 2k and 2k+1.

This module only holds tree-shape helpers (children/siblings by index and
looking up a node's hash from a built tree). Verification and close-proof
composition compose these with `merkle_tree.hash_bytes` /
`verify_proof_to_known_node` in the protocol layer.
"""

from __future__ import annotations

from .merkle_index import level_position_from_eytzinger


def max_k_for_depth(depth: int) -> int:
    """Largest payment index for a tree of the given depth (number of internal nodes).

    A tree with 2**depth leaves has 2**depth - 1 internal nodes (Eytzinger
    indexes 1..2**depth - 1); each is revealed by exactly one payment.
    """
    if depth < 0:
        raise ValueError("depth must be >= 0")
    return (1 << depth) - 1


def children_of_k(k: int) -> tuple[int, int]:
    """Eytzinger indexes of the two children of node k: (2k, 2k+1)."""
    if k < 1:
        raise ValueError("k must be >= 1")
    return 2 * k, 2 * k + 1


def sibling_of_k(k: int) -> int:
    """Eytzinger index of k's sibling (the other child of k's parent): k XOR 1.

    Undefined for the root (k=1), which has no sibling.
    """
    if k <= 1:
        raise ValueError("root (k=1) has no sibling")
    return k ^ 1


def node_hash_at_k(tree_levels: list[list[bytes]], depth: int, k: int) -> bytes:
    """Hash of the node at Eytzinger index k, read from a built tree (tree_levels[0] = leaves)."""
    level, position = level_position_from_eytzinger(k, depth)
    return tree_levels[level][position]
