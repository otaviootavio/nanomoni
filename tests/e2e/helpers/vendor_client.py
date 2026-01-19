"""VendorTestClient wraps vendor API operations for E2E tests."""

from __future__ import annotations

import aiohttp

from nanomoni.application.vendor.dtos import (
    VendorPublicKeyDTO,
    ReceivePaymentDTO,
    CloseChannelDTO,
    OffChainTxResponseDTO,
)
from nanomoni.application.vendor.payword_dtos import (
    ReceivePaywordPaymentDTO,
    PaywordPaymentResponseDTO,
)
from nanomoni.application.vendor.paytree_dtos import (
    ReceivePaytreePaymentDTO,
    PaytreePaymentResponseDTO,
)
from nanomoni.crypto.certificates import Envelope

from tests.e2e.helpers.http import AiohttpResponse


class VendorTestClient:
    """HTTP client for interacting with the Vendor API in E2E tests."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        http_client: aiohttp.ClientSession | None = None,
    ) -> None:
        """
        Initialize the vendor test client.

        Args:
            base_url: Base URL of the vendor API
            timeout: Request timeout in seconds
            http_client: Optional shared AsyncClient (reuses connections / keep-alive)
        """
        if not base_url:
            raise ValueError("VendorTestClient requires a non-empty base_url.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http_client = http_client

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
    ) -> AiohttpResponse:
        if self._http_client is not None:
            session = self._http_client
            close_session = False
        else:
            session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            close_session = True

        try:
            async with session.request(method, url, json=json) as resp:
                content = await resp.read()
                return AiohttpResponse(status_code=resp.status, content=content)
        finally:
            if close_session:
                await session.close()

    async def get_public_key(self) -> VendorPublicKeyDTO:
        """
        Get the vendor's public key.

        Returns:
            VendorPublicKeyDTO with vendor's public key in DER base64 format
        """
        response = await self._request("GET", f"{self.base_url}/vendor/keys/public")

        response.raise_for_status()
        return VendorPublicKeyDTO.model_validate(response.json())

    async def receive_payment(
        self, channel_id: str, payment_envelope: Envelope
    ) -> OffChainTxResponseDTO:
        """
        Submit a payment to the vendor.

        Args:
            channel_id: Payment channel computed ID
            payment_envelope: Signed payment envelope from client

        Returns:
            OffChainTxResponseDTO with payment details
        """
        dto = ReceivePaymentDTO(envelope=payment_envelope)
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/signature/{channel_id}/payments",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        return OffChainTxResponseDTO.model_validate(response.json())

    async def request_channel_closure(self, channel_id: str) -> None:
        """
        Request closure of a payment channel.

        Args:
            channel_id: Payment channel computed ID
        """
        dto = CloseChannelDTO(computed_id=channel_id)
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/signature/{channel_id}/closure-requests",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        assert response.status_code == 204

    async def receive_payword_payment(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> PaywordPaymentResponseDTO:
        """Submit a PayWord payment to the vendor."""
        dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        return PaywordPaymentResponseDTO.model_validate(response.json())

    async def receive_payword_payment_raw(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> AiohttpResponse:
        """
        Submit a PayWord payment to the vendor without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
        return await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
            json=dto.model_dump(),
        )

    async def request_channel_closure_payword(self, channel_id: str) -> None:
        """Request closure of a PayWord channel."""
        dto = CloseChannelDTO(computed_id=channel_id)
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/payword/{channel_id}/closure-requests",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        assert response.status_code == 204

    async def receive_paytree_payment(
        self, channel_id: str, *, i: int, leaf_b64: str, siblings_b64: list[str]
    ) -> PaytreePaymentResponseDTO:
        """Submit a PayTree payment to the vendor."""
        dto = ReceivePaytreePaymentDTO(
            i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/paytree/{channel_id}/payments",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        return PaytreePaymentResponseDTO.model_validate(response.json())

    async def receive_paytree_payment_raw(
        self, channel_id: str, *, i: int, leaf_b64: str, siblings_b64: list[str]
    ) -> AiohttpResponse:
        """
        Submit a PayTree payment to the vendor without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = ReceivePaytreePaymentDTO(
            i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        return await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/paytree/{channel_id}/payments",
            json=dto.model_dump(),
        )

    async def request_channel_closure_paytree(self, channel_id: str) -> None:
        """Request closure of a PayTree channel."""
        dto = CloseChannelDTO(computed_id=channel_id)
        response = await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/paytree/{channel_id}/closure-requests",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        assert response.status_code == 204

    async def receive_payment_raw(
        self, channel_id: str, payment_envelope: Envelope
    ) -> AiohttpResponse:
        """
        Submit a payment to the vendor without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = ReceivePaymentDTO(envelope=payment_envelope)
        return await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/signature/{channel_id}/payments",
            json=dto.model_dump(),
        )

    async def request_channel_closure_raw(self, channel_id: str) -> AiohttpResponse:
        """
        Request channel closure without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = CloseChannelDTO(computed_id=channel_id)
        return await self._request(
            "POST",
            f"{self.base_url}/vendor/channels/signature/{channel_id}/closure-requests",
            json=dto.model_dump(),
        )
