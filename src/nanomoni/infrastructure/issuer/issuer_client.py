from __future__ import annotations

from typing import Optional, Type
from types import TracebackType

from ...application.issuer.dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    IssuerPublicKeyDTO,
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    PaymentChannelResponseDTO,
)
from ..http.http_client import HttpClient, AsyncHttpClient


class IssuerClient:
    """Synchronous client for talking to the Issuer HTTP API.

    Methods are intentionally bound to the issuer application DTOs.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._http = HttpClient(base_url, timeout=timeout)

    def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        resp = self._http.post("/issuer/accounts", json=dto.model_dump())
        return RegistrationResponseDTO.model_validate(resp.json())

    def get_public_key(self) -> IssuerPublicKeyDTO:
        resp = self._http.get("/issuer/keys/public")
        return IssuerPublicKeyDTO.model_validate(resp.json())

    def open_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> OpenChannelResponseDTO:
        resp = self._http.post("/issuer/channels", json=dto.model_dump())
        return OpenChannelResponseDTO.model_validate(resp.json())

    def close_payment_channel(
        self,
        computed_id: str,
        dto: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        path = f"/issuer/channels/{computed_id}/settlements"
        resp = self._http.post(path, json=dto.model_dump())
        return CloseChannelResponseDTO.model_validate(resp.json())

    def get_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        path = f"/issuer/channels/{dto.computed_id}"
        resp = self._http.get(path)
        return PaymentChannelResponseDTO.model_validate(resp.json())

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "IssuerClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()


class AsyncIssuerClient:
    """Asynchronous client for talking to the Issuer HTTP API.

    Mirrors `IssuerClient` but uses `AsyncHttpClient` and async methods.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._http = AsyncHttpClient(base_url, timeout=timeout)

    async def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        resp = await self._http.post("/issuer/accounts", json=dto.model_dump())
        return RegistrationResponseDTO.model_validate(resp.json())

    async def get_public_key(self) -> IssuerPublicKeyDTO:
        resp = await self._http.get("/issuer/keys/public")
        return IssuerPublicKeyDTO.model_validate(resp.json())

    async def open_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> OpenChannelResponseDTO:
        resp = await self._http.post("/issuer/channels", json=dto.model_dump())
        return OpenChannelResponseDTO.model_validate(resp.json())

    async def close_payment_channel(
        self,
        computed_id: str,
        dto: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        path = f"/issuer/channels/{computed_id}/settlements"
        resp = await self._http.post(path, json=dto.model_dump())
        return CloseChannelResponseDTO.model_validate(resp.json())

    async def get_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        path = f"/issuer/channels/{dto.computed_id}"
        resp = await self._http.get(path)
        return PaymentChannelResponseDTO.model_validate(resp.json())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncIssuerClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()
