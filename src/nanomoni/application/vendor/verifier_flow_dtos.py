"""DTOs for the standalone Merkle prover/verifier flow."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SaveRootRequestDTO(BaseModel):
    """Request to save Merkle root for a tree."""

    root_b64: str = Field(..., description="Base64-encoded Merkle root")
    tree_size: int = Field(..., gt=0, description="Number of leaves (max_i + 1)")


class SaveLeafSubproofRequestDTO(BaseModel):
    """Request to verify and save a leaf sub-proof."""

    leaf_index: int = Field(..., ge=0, description="Leaf index")
    leaf_b64: str = Field(..., description="Base64-encoded leaf hash")
    siblings_b64: list[str] = Field(
        ..., description="List of base64-encoded sibling hashes for the auth path"
    )


class SaveLeafSubproofResponseDTO(BaseModel):
    """Response after successfully verifying and saving a leaf sub-proof."""

    tree_id: str
    leaf_index: int
    verified: bool = True
