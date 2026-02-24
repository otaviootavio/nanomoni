"""Use case for the standalone Merkle prover/verifier flow.

Mirrors the flow from test_prover_verifier_flow: save root, then verify and
save leaf sub-proofs. Uses verifier_repo_paytree_first_opt semantics via
the VerifierNodeRepository.
"""

from __future__ import annotations

from ....crypto.paytree_first_opt import (
    NoSubTreeForSubPathError,
    verifier_receive_leaf_subproof_b64,
    verifier_receive_root_b64,
)
from ....domain.vendor.verifier_node_repository import VerifierNodeRepository
from ..verifier_flow_dtos import (
    SaveLeafSubproofRequestDTO,
    SaveLeafSubproofResponseDTO,
    SaveRootRequestDTO,
)


class VerifierFlowService:
    """Service for the standalone Merkle verifier flow (save root, save leaf sub-proof)."""

    def __init__(self, node_repository: VerifierNodeRepository) -> None:
        self.node_repository = node_repository

    async def save_root(self, tree_id: str, dto: SaveRootRequestDTO) -> None:
        """Save Merkle root for a tree. Call before save_leaf_subproof."""
        node_repo = await self.node_repository.get_nodes(tree_id)
        verifier_receive_root_b64(node_repo, dto.root_b64, dto.tree_size)
        await self.node_repository.save_nodes(tree_id, node_repo)

    async def save_leaf_subproof(
        self, tree_id: str, dto: SaveLeafSubproofRequestDTO
    ) -> SaveLeafSubproofResponseDTO:
        """Verify leaf sub-proof and store nodes in the repository.

        Requires save_root to have been called first for this tree.
        Raises ValueError if proof is invalid or NoSubTreeForSubPathError
        if root was not saved.
        """
        node_repo = await self.node_repository.get_nodes(tree_id)
        try:
            verifier_receive_leaf_subproof_b64(
                repo=node_repo,
                leaf_index=dto.leaf_index,
                leaf_b64=dto.leaf_b64,
                siblings_b64=dto.siblings_b64,
            )
        except NoSubTreeForSubPathError:
            raise ValueError("no sub tree for that sub path")
        except ValueError as e:
            raise ValueError(str(e))

        await self.node_repository.save_nodes(tree_id, node_repo)
        return SaveLeafSubproofResponseDTO(
            tree_id=tree_id,
            leaf_index=dto.leaf_index,
            verified=True,
        )
