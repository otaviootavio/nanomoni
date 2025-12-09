from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    PaymentChannelResponseDTO,
)
from ..dependencies import get_payment_channel_service
from ....application.issuer.use_cases.payment_channel import PaymentChannelService

router = APIRouter(tags=["issuer"])


@router.post(
    "/payment-channel/open",
    response_model=OpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_payment_channel(
    payload: OpenChannelRequestDTO,
    service: PaymentChannelService = Depends(get_payment_channel_service),
) -> OpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/payment-channel/close",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def close_payment_channel(
    payload: CloseChannelRequestDTO,
    service: PaymentChannelService = Depends(get_payment_channel_service),
) -> CloseChannelResponseDTO:
    try:
        return await service.close_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/payment-channel/{computed_id}",
    response_model=PaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_payment_channel(
    computed_id: str,
    service: PaymentChannelService = Depends(get_payment_channel_service),
) -> PaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(computed_id=computed_id)
    return await service.get_channel(payload)
