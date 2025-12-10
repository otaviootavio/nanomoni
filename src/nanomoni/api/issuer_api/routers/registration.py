from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    IssuerPublicKeyDTO,
)
from ..dependencies import get_issuer_service
from ....application.issuer.use_cases.registration import RegistrationService

router = APIRouter(tags=["issuer"])


@router.post(
    "/accounts",
    response_model=RegistrationResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegistrationRequestDTO,
    service: RegistrationService = Depends(get_issuer_service),
) -> RegistrationResponseDTO:
    try:
        return await service.register(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/keys/public",
    response_model=IssuerPublicKeyDTO,
    status_code=status.HTTP_200_OK,
)
async def get_public_key(
    service: RegistrationService = Depends(get_issuer_service),
) -> IssuerPublicKeyDTO:
    return service.get_issuer_public_key()
