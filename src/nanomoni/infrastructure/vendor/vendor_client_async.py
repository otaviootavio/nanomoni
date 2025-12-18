from __future__ import annotations

from typing import Optional, Type
from types import TracebackType

from ...application.vendor.dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
    VendorPublicKeyDTO,
)
from ..http.http_client import AsyncHttpClient


class VendorClientAsync:
    """Asynchronous client for talking to the Vendor HTTP API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        # vendor_base_url is expected to already contain any API prefix (e.g. /api/v1)
        self._http = AsyncHttpClient(base_url, timeout=timeout)

    async def get_vendor_public_key(self) -> VendorPublicKeyDTO:
        """Fetch the vendor's public key (DER b64) from the vendor API.

        The JSON response is validated into ``VendorPublicKeyDTO`` to ensure
        runtime contract compliance.
        """
        resp = await self._http.get("/vendor/keys/public")
        return VendorPublicKeyDTO.model_validate(resp.json())

    async def send_off_chain_payment(
        self,
        computed_id: str,
        dto: ReceivePaymentDTO,
    ) -> OffChainTxResponseDTO:
        """Send an off-chain payment to the vendor API.

        Uses ``ReceivePaymentDTO`` as the request body and validates the response
        as ``OffChainTxResponseDTO`` to keep this client aligned with the
        vendor API contract.
        """
        path = f"/vendor/channels/{computed_id}/payments"
        resp = await self._http.post(path, json=dto.model_dump())
        return OffChainTxResponseDTO.model_validate(resp.json())

    async def request_close_channel(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to close a payment channel."""
        path = f"/vendor/channels/{dto.computed_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "VendorClientAsync":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.aclose()
