from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.issuer.dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    IssuerPublicKeyDTO,
)
from ..dependencies import get_issuer_service
from ....application.issuer.use_cases.registration import RegistrationService
from ....domain.errors import AccountNotFoundError

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


@router.get(
    "/accounts",
    response_model=RegistrationResponseDTO,
    status_code=status.HTTP_200_OK,
)
async def get_account(
    public_key_der_b64: str,
    service: RegistrationService = Depends(get_issuer_service),
) -> RegistrationResponseDTO:
    """
    Fetch account state (balance) by public key.

    Uses a query parameter instead of a path parameter because DER base64 often
    contains '/' and '+' which are awkward in URLs.
    """
    try:
        normalized_public_key_der_b64 = public_key_der_b64.strip().replace(" ", "+")
        return await service.get_account(normalized_public_key_der_b64)
    except AccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
