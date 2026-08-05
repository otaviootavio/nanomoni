"""PayTree child-pair protocol: per-payment child reveal + frontier close proof.

Per payment k, the client reveals the two children of node k (Eytzinger
index); the vendor accepts iff H(left, right) equals the hash it already
knows for node k, then learns nodes 2k and 2k+1. Closing sends the most
recently revealed child pair plus one "outer" sibling per remaining level up
to the root, letting the issuer recompute the root in O(log N) without ever
receiving a full per-payment proof.
"""

from __future__ import annotations

from ..crypto.merkle_tree import hash_bytes, verify_proof_to_known_node
from ..crypto.paytree_child_pair import children_of_k, sibling_of_k


def verify_payment(known_parent: bytes, left: bytes, right: bytes) -> bool:
    """Verify that (left, right) are the children of a node already known to equal known_parent."""
    return hash_bytes(left + right) == known_parent


def build_close_proof(
    k: int, known: dict[int, bytes]
) -> tuple[bytes, bytes, list[bytes]]:
    """Build the frontier close proof for the vendor's most recently paid node k.

    Returns (left, right, siblings) where (left, right) are the children of k
    and siblings are the outer-sibling hashes walking from k up to (but not
    including) the root, one per level. Raises KeyError if a required node is
    missing from `known` (e.g. an out-of-order or incomplete payment history).
    """
    left_k, right_k = children_of_k(k)
    left = known[left_k]
    right = known[right_k]

    siblings: list[bytes] = []
    current = k
    while current != 1:
        siblings.append(known[sibling_of_k(current)])
        current //= 2
    return left, right, siblings


def verify_close_proof(
    root: bytes,
    k: int,
    left: bytes,
    right: bytes,
    siblings: list[bytes],
) -> bool:
    """Verify a frontier close proof: combine (left, right) into h_k, then walk to root.

    Reuses `verify_proof_to_known_node`: h_k plays the role of the "leaf" hash
    and k plays the role of the "leaf index" — the same even/odd-index parity
    rule that picks combine order for a leaf's authentication path applies
    identically when climbing from any Eytzinger index k to the root.

    The number of hops from k to the root (Eytzinger index 1) is fixed by k
    itself (k.bit_length() - 1) and MUST NOT be taken from len(siblings): a
    caller-controlled sibling count lets an attacker claim an inflated k that
    is merely congruent to the real k modulo 2**len(siblings), which replays
    the same hash chain without ever having reached the real root at k's true
    depth. Rejecting any sibling count that doesn't match k's true distance
    to the root closes that alias.
    """
    if k < 1:
        return False
    expected_hops = k.bit_length() - 1
    if len(siblings) != expected_hops:
        return False
    node = hash_bytes(left + right)
    return verify_proof_to_known_node(
        leaf_hash=node,
        leaf_index=k,
        siblings=siblings,
        known_node_hash=root,
        known_node_level=expected_hops,
    )
