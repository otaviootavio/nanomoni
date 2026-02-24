"""Verifier node repository interface for Merkle tree prover/verifier flow.

Stores Merkle tree nodes (root, leaf hashes, sibling hashes) keyed by level:position.
Backed by verifier_repo_paytree_first_opt semantics. Used by the standalone
prover/verifier flow (save root, save leaf sub-proof) without payment context.
"""

from __future__ import annotations

from abc import abstractmethod


class VerifierNodeRepository:
    """Repository for persisting verifier node storage per tree."""

    @abstractmethod
    async def get_nodes(self, tree_id: str) -> dict[str, str]:
        """Get all stored nodes for a tree. Returns empty dict if none."""
        pass

    @abstractmethod
    async def save_nodes(self, tree_id: str, nodes: dict[str, str]) -> None:
        """Persist nodes for a tree. Overwrites existing."""
        pass
