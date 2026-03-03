"""Shared PayTree proof verification using the protocol layer."""

from __future__ import annotations

from nanomoni.crypto.paytree import b64_to_bytes
from nanomoni.protocol import subroot_index_standard, verify_proof_with_leaf_hash


def verify_paytree_proof_standard(
    *,
    i: int,
    leaf_b64: str,
    siblings_b64: list[str],
    root_b64: str,
    max_i: int,
) -> bool:
    """Verify a standard PayTree proof (leaf -> root) using the protocol layer."""
    try:
        leaf_hash = b64_to_bytes(leaf_b64)
        siblings = [b64_to_bytes(s) for s in siblings_b64]
        root = b64_to_bytes(root_b64)
    except Exception:
        return False
    # Tree is padded to next power of 2; depth = ceil(log2(max_i+1))
    depth = max_i.bit_length() if max_i > 0 else 0
    subroot_index = subroot_index_standard(depth)
    return verify_proof_with_leaf_hash(
        leaf_hash=leaf_hash,
        leaf_index=i,
        siblings=siblings,
        subroot_node=root,
        subroot_index=subroot_index,
        depth=depth,
    )
