"""Payment API routes (Vendor)."""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from cryptography.exceptions import InvalidSignature

from ....application.vendor_dtos import ReceivePaymentDTO, OffChainTxResponseDTO
from ....application.vendor_use_case import PaymentService
from ..dependencies import get_payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/receive",
    response_model=OffChainTxResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_payment(
    payment_data: ReceivePaymentDTO,
    payment_service: PaymentService = Depends(get_payment_service),
) -> OffChainTxResponseDTO:
    """Receive and validate an off-chain payment from a client."""
    try:
        return await payment_service.receive_payment(payment_data)
    except InvalidSignature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature on payment envelope",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process payment: {str(e)}",
        )


@router.get("/{payment_id}", response_model=OffChainTxResponseDTO)
async def get_payment(
    payment_id: UUID, payment_service: PaymentService = Depends(get_payment_service)
) -> OffChainTxResponseDTO:
    """Get an off-chain payment by ID."""
    payment = await payment_service.get_payment_by_id(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )
    return payment


@router.get("/channel/{computed_id}", response_model=List[OffChainTxResponseDTO])
async def get_payments_by_channel(
    computed_id: str,
    payment_service: PaymentService = Depends(get_payment_service),
) -> List[OffChainTxResponseDTO]:
    """Get all payments for a specific payment channel."""
    return await payment_service.get_payments_by_channel(computed_id)
