"""Rebuild a full leaf→root PayTree proof from a sparse node store.

Two independent implementations, one per scheme (no shared class/inheritance
between the payment services, so their rebuild strategies are independent
too — deliberately duplicated rather than parameterizing one function):

- Second-opt (``rebuild_full_paytree_proof`` / ``_resolve_missing``) persists
  P *and* Q (the computed ancestor hashes from verification) on every
  payment, so its settle-time rebuild is expected to resolve in exactly one
  repository read — a target the store doesn't hold at its own granularity
  is treated as a genuine, unrecoverable miss, not a cue to keep reading.
- First-opt (``rebuild_full_paytree_proof_first_opt`` / rest of this file)
  persists P only, so its settle-time rebuild must reconstruct higher-level
  siblings from finer-grained pieces accumulated across several payments:
  an unresolved target expands to its two children for a further round,
  bounded by ``depth`` rounds total, each one batched ``get_nodes`` call —
  still failing outright if the frontier bottoms out at a leaf with no data
  anywhere.
"""

from __future__ import annotations

from typing import Optional

from ...crypto.merkle_index import compute_tree_depth, key_eytzinger
from ...crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    combine_children,
)
from ...crypto.paytree import b64_to_bytes, bytes_to_b64
from ...domain.vendor.entities import PaymentChannel
from ...domain.vendor.merkle_node_repository import MerkleNodeRepository

NodeIndex = tuple[int, int]


async def _resolve_missing(
    node_repo: MerkleNodeRepository,
    channel_id: str,
    depth: int,
    targets: set[NodeIndex],
    known: dict[NodeIndex, bytes],
    extra_nodes_b64: dict[str, str],
    root_hash: Optional[bytes],
) -> bool:
    """Populate ``known`` for every node in ``targets``, in exactly one
    repository read.

    Each target is resolved from ``extra_nodes_b64``, the root special-case,
    or a single batched ``get_nodes`` call for whatever's left — never by
    decomposing an unresolved target into its children for a further round
    trip. A target the store doesn't hold at its own granularity is a genuine
    miss, not a cue to keep reading: the caller must fail rather than the
    rebuild silently costing an unbounded number of reads.

    Returns False if any target remains unresolved after that one read.
    """
    to_fetch: dict[str, NodeIndex] = {}
    for lev, pos in targets:
        if (lev, pos) in known:
            continue
        node_key = key_eytzinger(lev, pos, depth)
        b64 = extra_nodes_b64.get(node_key)
        if b64:
            known[(lev, pos)] = b64_to_bytes(b64)
        elif lev == depth and pos == 0 and root_hash is not None:
            known[(lev, pos)] = root_hash
        else:
            to_fetch[node_key] = (lev, pos)

    if to_fetch:
        fetched = await node_repo.get_nodes(channel_id, list(to_fetch))
        for node_key, b64 in fetched.items():
            if b64:
                known[to_fetch[node_key]] = b64_to_bytes(b64)

    return all((lev, pos) in known for lev, pos in targets)


async def rebuild_full_paytree_proof(
    node_repo: MerkleNodeRepository,
    channel_id: str,
    channel: PaymentChannel,
    last_i: int,
    last_leaf_b64: str,
    *,
    extra_nodes_b64: Optional[dict[str, str]] = None,
) -> Optional[tuple[str, list[str]]]:
    """Reconstruct the full leaf→root sibling proof for leaf ``last_i``.

    ``extra_nodes_b64`` (e.g. a caller's just-fetched/just-written nodes) is
    consulted before falling back to a repository read, so a caller that
    already holds some of the dependency nodes in memory avoids re-fetching
    them. Returns None if a required dependency node is missing anywhere.
    """
    depth = compute_tree_depth(channel.max_steps)
    full_sibling_indexes = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, last_i, depth, 0
    )

    known: dict[NodeIndex, bytes] = {}
    extra_nodes_b64 = extra_nodes_b64 or {}
    root_hash = b64_to_bytes(channel.commitment) if channel.commitment else None

    ok = await _resolve_missing(
        node_repo,
        channel_id,
        depth,
        set(full_sibling_indexes),
        known,
        extra_nodes_b64,
        root_hash,
    )
    if not ok:
        return None

    full_siblings = [known[lev, pos] for lev, pos in full_sibling_indexes]
    return last_leaf_b64, [bytes_to_b64(s) for s in full_siblings]


async def _resolve_missing_first_opt(
    node_repo: MerkleNodeRepository,
    channel_id: str,
    depth: int,
    targets: set[NodeIndex],
    known: dict[NodeIndex, bytes],
    extra_nodes_b64: dict[str, str],
    root_hash: Optional[bytes],
) -> bool:
    """Populate ``known`` for every node in ``targets`` (and any ancestors of
    theirs already resolvable), expanding downward level-by-level.

    One batched ``get_nodes`` call per tree level, instead of one call per
    node: the first pass tries to resolve ``targets`` directly; whatever
    isn't found expands to its two children (one level closer to the
    leaves) and the next pass batch-fetches *that* whole frontier in a
    single round trip. Bounded by ``depth`` round trips total, each a single
    multi-key MGET.

    Returns False if the frontier bottoms out at a leaf-level node with no
    data anywhere (a genuine, unrecoverable miss).
    """
    frontier = {t for t in targets if t not in known}
    while frontier:
        to_fetch: dict[str, NodeIndex] = {}
        for lev, pos in frontier:
            node_key = key_eytzinger(lev, pos, depth)
            b64 = extra_nodes_b64.get(node_key)
            if b64:
                known[(lev, pos)] = b64_to_bytes(b64)
            elif lev == depth and pos == 0 and root_hash is not None:
                known[(lev, pos)] = root_hash
            else:
                to_fetch[node_key] = (lev, pos)

        if to_fetch:
            fetched = await node_repo.get_nodes(channel_id, list(to_fetch))
            for node_key, b64 in fetched.items():
                if b64:
                    known[to_fetch[node_key]] = b64_to_bytes(b64)

        next_frontier: set[NodeIndex] = set()
        for lev, pos in frontier:
            if (lev, pos) in known:
                continue
            if lev == 0:
                return False
            next_frontier.add((lev - 1, 2 * pos))
            next_frontier.add((lev - 1, 2 * pos + 1))
        frontier = next_frontier

    return True


def _combine_first_opt(
    level: int,
    position: int,
    known: dict[NodeIndex, bytes],
) -> bytes:
    """Recombine (level, position) bottom-up from ``known`` (fully populated
    by ``_resolve_missing_first_opt`` — no store access here, pure in-memory
    hashing).
    """
    key = (level, position)
    if key in known:
        return known[key]
    left = _combine_first_opt(level - 1, 2 * position, known)
    right = _combine_first_opt(level - 1, 2 * position + 1, known)
    h = combine_children(left, right, True)
    known[key] = h
    return h


async def rebuild_full_paytree_proof_first_opt(
    node_repo: MerkleNodeRepository,
    channel_id: str,
    channel: PaymentChannel,
    last_i: int,
    last_leaf_b64: str,
    *,
    extra_nodes_b64: Optional[dict[str, str]] = None,
) -> Optional[tuple[str, list[str]]]:
    """Reconstruct the full leaf→root sibling proof for leaf ``last_i``
    (first-opt: P-only node store, so this may need several rounds of
    decomposition — see ``_resolve_missing_first_opt``).

    ``extra_nodes_b64`` (e.g. a caller's just-fetched/just-written nodes) is
    consulted before falling back to a repository read, so a caller that
    already holds some of the dependency nodes in memory avoids re-fetching
    them. Returns None if a required dependency node is missing anywhere.
    """
    depth = compute_tree_depth(channel.max_steps)
    full_sibling_indexes = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, last_i, depth, 0
    )

    known: dict[NodeIndex, bytes] = {(0, last_i): b64_to_bytes(last_leaf_b64)}
    extra_nodes_b64 = extra_nodes_b64 or {}
    root_hash = b64_to_bytes(channel.commitment) if channel.commitment else None

    ok = await _resolve_missing_first_opt(
        node_repo,
        channel_id,
        depth,
        set(full_sibling_indexes),
        known,
        extra_nodes_b64,
        root_hash,
    )
    if not ok:
        return None

    full_siblings = [
        _combine_first_opt(lev, pos, known) for lev, pos in full_sibling_indexes
    ]
    return last_leaf_b64, [bytes_to_b64(s) for s in full_siblings]
