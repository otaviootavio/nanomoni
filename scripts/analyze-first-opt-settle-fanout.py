"""Size the single MGET that paytree_first_opt settlement issues per channel.

_rebuild_paytree_proof_for_settlement expands every sibling on the last leaf's
root path into that sibling's whole subtree (get_node_dependency_indexes), then
batch-reads the union in one call. This prints how many keys that is for each
rung of run_benchmark.sh, next to how many nodes actually exist.

Read-only: pure computation over the project's own index helpers.
"""

from __future__ import annotations

from nanomoni.crypto.merkle_index import compute_tree_depth, key_eytzinger
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    get_proof_dependency_indexes,
)

TPS_VALUES = [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
RUN_DURATION_SEC = 600
TPS_PER_CLIENT = 256

# merkle_node:{uuid4}:{eytzinger} -- 12 + 36 + 1 + (depth+1) chars.
KEY_OVERHEAD = 12 + 36 + 1
VALUE_BYTES = 44  # base64 sha256


def main() -> None:
    hdr = (
        f"{'tps':>5s} {'total':>9s} {'vc':>3s} {'max_i':>8s} {'depth':>5s} "
        f"{'mget_keys':>11s} {'nodes_live':>11s} {'req_MiB':>8s} "
        f"{'reply_MiB':>9s} {'xN_clients':>10s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for tps in TPS_VALUES:
        total = tps * RUN_DURATION_SEC
        vc = max(1, tps // TPS_PER_CLIENT)
        max_i = total // vc
        depth = compute_tree_depth(max_i)

        siblings = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
            0, max_i, depth, 0
        )
        deps = get_proof_dependency_indexes(siblings, depth)
        n_keys = len(deps)

        # Only nodes actually persisted by payments come back non-nil: the leaf
        # plus its revealed siblings, ~2 per payment for a sequential scan.
        nodes_live = min(n_keys, 2 * max_i)

        key_len = KEY_OVERHEAD + len(key_eytzinger(0, 0, depth))
        req_mib = n_keys * key_len / 1024 / 1024
        reply_mib = nodes_live * VALUE_BYTES / 1024 / 1024

        print(
            f"{tps:5d} {total:9d} {vc:3d} {max_i:8d} {depth:5d} "
            f"{n_keys:11,d} {nodes_live:11,d} {req_mib:8.1f} "
            f"{reply_mib:9.1f} {req_mib * vc + reply_mib * vc:10.1f}"
        )


if __name__ == "__main__":
    main()
