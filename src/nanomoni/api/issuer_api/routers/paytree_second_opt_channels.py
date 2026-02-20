"""PayTree Second Opt channel API routes (Issuer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
)
from ....application.issuer.paytree_second_opt_dtos import (
    PaytreeSecondOptOpenChannelResponseDTO,
    PaytreeSecondOptPaymentChannelResponseDTO,
    PaytreeSecondOptSettlementRequestDTO,
)
from ....application.issuer.use_cases.paytree_second_opt_channel import (
    PaytreeSecondOptChannelService,
)
from ..dependencies import get_paytree_second_opt_channel_service

router = APIRouter(tags=["channels", "paytree_second_opt"])


@router.post(
    "/channels/paytree_second_opt",
    response_model=PaytreeSecondOptOpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_paytree_second_opt_channel(
    payload: OpenChannelRequestDTO,
    service: PaytreeSecondOptChannelService = Depends(
        get_paytree_second_opt_channel_service
    ),
) -> PaytreeSecondOptOpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/channels/paytree_second_opt/{channel_id}/settlements",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def settle_paytree_second_opt_channel(
    channel_id: str,
    payload: PaytreeSecondOptSettlementRequestDTO,
    service: PaytreeSecondOptChannelService = Depends(
        get_paytree_second_opt_channel_service
    ),
) -> CloseChannelResponseDTO:
    try:
        return await service.settle_channel(channel_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/channels/paytree_second_opt/{channel_id}",
    response_model=PaytreeSecondOptPaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_paytree_second_opt_channel(
    channel_id: str,
    service: PaytreeSecondOptChannelService = Depends(
        get_paytree_second_opt_channel_service
    ),
) -> PaytreeSecondOptPaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(channel_id=channel_id)
    try:
        return await service.get_channel(payload)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
