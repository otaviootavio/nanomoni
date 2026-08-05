"""PayTree child-pair channel API routes (Issuer).

Opening/reading a child-pair channel reuses the same PayTree commitment shape
(root/unit_value/max) as std and first-opt — only per-payment verification
and settlement differ, so this router shares `PaytreeChannelService.open_channel`
/ `get_channel` and adds a dedicated child-pair settlement endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
    CloseChannelResponseDTO,
)
from ....application.issuer.paytree_dtos import (
    PaytreeChildPairSettlementRequestDTO,
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
)
from ....application.issuer.use_cases.paytree_channel import PaytreeChannelService
from ..dependencies import get_paytree_child_pair_channel_service


router = APIRouter(
    prefix="/channels/paytree/child-pair", tags=["channels", "paytree-child-pair"]
)


@router.post(
    "",
    response_model=PaytreeOpenChannelResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def open_paytree_child_pair_channel(
    payload: OpenChannelRequestDTO,
    service: PaytreeChannelService = Depends(get_paytree_child_pair_channel_service),
) -> PaytreeOpenChannelResponseDTO:
    try:
        return await service.open_channel(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{channel_id}/settlements",
    response_model=CloseChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def settle_paytree_child_pair_channel(
    channel_id: str,
    payload: PaytreeChildPairSettlementRequestDTO,
    service: PaytreeChannelService = Depends(get_paytree_child_pair_channel_service),
) -> CloseChannelResponseDTO:
    try:
        return await service.settle_channel_child_pair(channel_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{channel_id}",
    response_model=PaytreePaymentChannelResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_paytree_child_pair_channel(
    channel_id: str,
    service: PaytreeChannelService = Depends(get_paytree_child_pair_channel_service),
) -> PaytreePaymentChannelResponseDTO:
    payload = GetPaymentChannelRequestDTO(channel_id=channel_id)
    try:
        return await service.get_channel(payload)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
