"""Would a direct read of the last leaf's root-path siblings suffice at
settlement, instead of expanding every sibling into its whole subtree?

Replays the sequential first-opt scan the benchmark client performs, accumulates
exactly the node keys the vendor persists (build_node_updates), then checks
whether the settlement proof's sibling indexes are already among them.

Read-only: pure computation over the project's own index helpers.
"""

from __future__ import annotations

from nanomoni.crypto.merkle_index import compute_tree_depth
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    get_proof_dependency_indexes,
    proof_indexes_first_opt,
)

CASES = [(4800, 1), (38400, 1), (153600, 1), (153600, 16)]


def main() -> None:
    for max_i, vc in CASES:
        depth = compute_tree_depth(max_i)

        # What the vendor ends up holding after the client's sequential scan:
        # every payment persists its leaf plus each sibling in its pruned proof.
        stored: set[tuple[int, int]] = set()
        prior: list[int] = []
        for i in range(1, max_i + 1):
            stored.add((0, i))
            stored.update(proof_indexes_first_opt(i, prior, depth))
            prior = [i]

        # What settlement needs vs what it actually reads today.
        needed = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
            0, max_i, depth, 0
        )
        fetched = get_proof_dependency_indexes(needed, depth)
        missing = [idx for idx in needed if idx not in stored]

        # Alternative: descend from each needed sibling and stop as soon as a
        # node is cached, instead of pulling its entire subtree unconditionally.
        # One MGET per level; count every key such a walk would touch.
        visited: set[tuple[int, int]] = set()
        frontier = list(needed)
        levels = 0
        while frontier:
            levels += 1
            nxt = []
            for lev, pos in frontier:
                if (lev, pos) in visited:
                    continue
                visited.add((lev, pos))
                if (lev, pos) in stored or lev == 0:
                    continue
                nxt.extend([(lev - 1, 2 * pos), (lev - 1, 2 * pos + 1)])
            frontier = nxt

        print(
            f"max_i={max_i:>7d} vc={vc:<3d} depth={depth:<3d} "
            f"stored={len(stored):>8,d} | settlement needs {len(needed):>3d} "
            f"siblings | today reads {len(fetched):>9,d} keys "
            f"({len(fetched) / len(needed):>8,.0f}x) | "
            f"cached {len(needed) - len(missing)}/{len(needed)} | "
            f"lazy descent reads {len(visited):>6,d} keys in {levels} round trips"
        )
        if missing:
            print(f"    not cached (must be recomputed): {missing}")


if __name__ == "__main__":
    main()
