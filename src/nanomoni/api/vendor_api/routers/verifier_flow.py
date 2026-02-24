"""Merkle prover/verifier flow API routes (standalone, no payment context)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from ....application.vendor.use_cases.verifier_flow_service import VerifierFlowService
from ....application.vendor.verifier_flow_dtos import (
    SaveLeafSubproofRequestDTO,
    SaveLeafSubproofResponseDTO,
    SaveRootRequestDTO,
)
from ..dependencies import get_verifier_flow_service

router = APIRouter(
    prefix="/merkle",
    tags=["merkle", "verifier_flow"],
)


@router.post(
    "/{tree_id}/root",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def save_root(
    payload: SaveRootRequestDTO,
    tree_id: str = Path(
        ..., description="Tree identifier (e.g. session or channel id)"
    ),
    service: VerifierFlowService = Depends(get_verifier_flow_service),
) -> None:
    """Save Merkle root for a tree. Call before submitting leaf sub-proofs."""
    try:
        await service.save_root(tree_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{tree_id}/leaf-subproof",
    response_model=SaveLeafSubproofResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def save_leaf_subproof(
    payload: SaveLeafSubproofRequestDTO,
    tree_id: str = Path(..., description="Tree identifier"),
    service: VerifierFlowService = Depends(get_verifier_flow_service),
) -> SaveLeafSubproofResponseDTO:
    """Verify and save a leaf sub-proof. Root must have been saved first."""
    try:
        return await service.save_leaf_subproof(tree_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
