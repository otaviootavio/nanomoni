"""PayTree First Opt channel API routes (Issuer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
)
from ....application.issuer.paytree_first_opt_dtos import (
    PaytreeFirstOptOpenChannelResponseDTO,
    PaytreeFirstOptPaymentChannelResponseDTO,
    PaytreeFirstOptSettlementRequestDTO,
)
from ....application.issuer.use_cases.paytree_first_opt_channel import (
    PaytreeFirstOptChannelService,
)
from ..dependencies import get_paytree_first_opt_channel_service

router = APIRouter(tags=["channels", "paytree_first_opt"])


@router.post(
    "/channels/paytree_first_opt",
    response_model=PaytreeFirstOptOpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_paytree_first_opt_channel(
    payload: OpenChannelRequestDTO,
    service: PaytreeFirstOptChannelService = Depends(
        get_paytree_first_opt_channel_service
    ),
) -> PaytreeFirstOptOpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/channels/paytree_first_opt/{channel_id}/settlements",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def settle_paytree_first_opt_channel(
    channel_id: str,
    payload: PaytreeFirstOptSettlementRequestDTO,
    service: PaytreeFirstOptChannelService = Depends(
        get_paytree_first_opt_channel_service
    ),
) -> CloseChannelResponseDTO:
    try:
        return await service.settle_channel(channel_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/channels/paytree_first_opt/{channel_id}",
    response_model=PaytreeFirstOptPaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_paytree_first_opt_channel(
    channel_id: str,
    service: PaytreeFirstOptChannelService = Depends(
        get_paytree_first_opt_channel_service
    ),
) -> PaytreeFirstOptPaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(channel_id=channel_id)
    try:
        return await service.get_channel(payload)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
