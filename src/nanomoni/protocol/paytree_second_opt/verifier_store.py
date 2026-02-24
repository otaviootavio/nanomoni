"""Verifier node storage for PayTree second-opt.

Second-opt semantics: store proof data (leaf + siblings) AND computed path nodes (Q).
Same flow as first-opt (pruned proof → retrieve missing from repo → validate full proof),
but the repo accumulates both P(x) and Q(x) so later proofs can verify to a known sub-root
and send fewer sibling levels.

Keys: "level:position" (e.g. "0:3", "2:1").
"""

from __future__ import annotations

import base64
from typing import MutableMapping, Optional

from ...crypto.merkle_index import (
    compute_tree_depth,
    get_ancestor_at_level,
    get_sibling_position_at_level,
    key,
)
from ...crypto.merkle_tree import combine_children

VerifierRepoData = dict[str, str]
"""Verifier store data: key (level:position) -> base64 hash."""


def _compute_path_nodes(
    leaf_index: int, leaf_hash: bytes, siblings: list[bytes]
) -> dict[str, bytes]:
    """Compute path nodes from leaf up to root (Q(x)) for second-opt."""
    path: dict[str, bytes] = {}
    current = leaf_hash
    current_index = leaf_index
    for level, sibling in enumerate(siblings):
        left_is_first = (current_index % 2) == 0
        parent = combine_children(current, sibling, left_is_first)
        parent_pos = get_ancestor_at_level(leaf_index, level + 1)
        path[key(level + 1, parent_pos)] = parent
        current = parent
        current_index = current_index // 2
    return path


def store_root(repo: MutableMapping[str, str], root_b64: str, tree_size: int) -> None:
    """Store Merkle root in repo."""
    max_i = tree_size - 1
    depth = compute_tree_depth(max_i)
    repo[key(depth, 0)] = root_b64


def store_proof_with_path(
    repo: MutableMapping[str, str],
    leaf_index: int,
    leaf_b64: str,
    siblings_b64: list[str],
) -> None:
    """Store leaf, sibling hashes (P), and computed path nodes (Q) from a verified proof.

    Second-opt: proof path + computed path so later pruned proofs can use known sub-roots
    and omit levels already in repo (P ∪ Q).
    """
    repo[key(0, leaf_index)] = leaf_b64
    for level, sibling_b64 in enumerate(siblings_b64):
        sibling_pos = get_sibling_position_at_level(leaf_index, level)
        repo[key(level, sibling_pos)] = sibling_b64
    leaf_hash = base64.b64decode(leaf_b64, validate=True)
    siblings = [base64.b64decode(s, validate=True) for s in siblings_b64]
    for k, v in _compute_path_nodes(leaf_index, leaf_hash, siblings).items():
        repo[k] = base64.b64encode(v).decode("utf-8")


def get_node(
    repo: MutableMapping[str, str], level: int, position: int
) -> Optional[str]:
    """Get node hash (base64) by level and position. Returns None if not found."""
    return repo.get(key(level, position))
