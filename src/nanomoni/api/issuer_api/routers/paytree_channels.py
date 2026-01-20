"""PayTree channel API routes (Issuer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
    CloseChannelResponseDTO,
)
from ....application.issuer.paytree_dtos import (
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
    PaytreeSettlementRequestDTO,
)
from ....application.issuer.use_cases.paytree_channel import PaytreeChannelService
from ..dependencies import get_paytree_channel_service


router = APIRouter(tags=["channels", "paytree"])


@router.post(
    "/channels/paytree",
    response_model=PaytreeOpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_paytree_channel(
    payload: OpenChannelRequestDTO,
    service: PaytreeChannelService = Depends(get_paytree_channel_service),
) -> PaytreeOpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/channels/paytree/{channel_id}/settlements",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def settle_paytree_channel(
    channel_id: str,
    payload: PaytreeSettlementRequestDTO,
    service: PaytreeChannelService = Depends(get_paytree_channel_service),
) -> CloseChannelResponseDTO:
    try:
        return await service.settle_channel(channel_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/channels/paytree/{channel_id}",
    response_model=PaytreePaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_paytree_channel(
    channel_id: str,
    service: PaytreeChannelService = Depends(get_paytree_channel_service),
) -> PaytreePaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(channel_id=channel_id)
    try:
        return await service.get_channel(payload)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
