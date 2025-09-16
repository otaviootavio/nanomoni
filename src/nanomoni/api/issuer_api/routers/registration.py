from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer_dtos import (
    StartRegistrationRequestDTO,
    StartRegistrationResponseDTO,
    CompleteRegistrationRequestDTO,
    RegistrationCertificateDTO,
    IssuerPublicKeyDTO,
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
)
from ..dependencies import get_issuer_service, get_payment_channel_service
from ....application.issuer_use_case import IssuerService
from ....application.issuer.use_cases.payment_channel import PaymentChannelService

router = APIRouter(tags=["issuer-registration"])


@router.post(
    "/registration/start",
    response_model=StartRegistrationResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def start_registration(
    payload: StartRegistrationRequestDTO,
    service: IssuerService = Depends(get_issuer_service),
) -> StartRegistrationResponseDTO:
    try:
        return await service.start_registration(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/registration/complete",
    response_model=RegistrationCertificateDTO,
    status_code=status.HTTP_201_CREATED,
)
async def complete_registration(
    payload: CompleteRegistrationRequestDTO,
    service: IssuerService = Depends(get_issuer_service),
) -> RegistrationCertificateDTO:
    try:
        return await service.complete_registration(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/public-key",
    response_model=IssuerPublicKeyDTO,
    status_code=status.HTTP_200_OK,
)
async def get_public_key(
    service: IssuerService = Depends(get_issuer_service),
) -> IssuerPublicKeyDTO:
    return service.get_issuer_public_key()


# Payment channel routes
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
