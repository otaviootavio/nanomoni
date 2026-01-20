from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.dtos import OpenChannelRequestDTO, CloseChannelResponseDTO
from ....application.issuer.payword_dtos import (
    PaywordOpenChannelResponseDTO,
    PaywordPaymentChannelResponseDTO,
    PaywordSettlementRequestDTO,
)
from ....application.issuer.use_cases.payword_channel import PaywordChannelService
from ..dependencies import get_payword_channel_service


router = APIRouter(tags=["channels", "payword"])


@router.post(
    "/channels/payword",
    response_model=PaywordOpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_payword_channel(
    payload: OpenChannelRequestDTO,
    service: PaywordChannelService = Depends(get_payword_channel_service),
) -> PaywordOpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/channels/payword/{channel_id}/settlements",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def settle_payword_channel(
    channel_id: str,
    payload: PaywordSettlementRequestDTO,
    service: PaywordChannelService = Depends(get_payword_channel_service),
) -> CloseChannelResponseDTO:
    try:
        return await service.settle_channel(channel_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/channels/payword/{channel_id}",
    response_model=PaywordPaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_payword_channel(
    channel_id: str,
    service: PaywordChannelService = Depends(get_payword_channel_service),
) -> PaywordPaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(channel_id=channel_id)
    try:
        return await service.get_channel(payload)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
