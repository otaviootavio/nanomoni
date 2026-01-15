"""VendorTestClient wraps vendor API operations for E2E tests."""

from __future__ import annotations

import httpx

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
from nanomoni.crypto.certificates import Envelope


class VendorTestClient:
    """HTTP client for interacting with the Vendor API in E2E tests."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        http_client: httpx.AsyncClient | None = None,
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

    async def get_public_key(self) -> VendorPublicKeyDTO:
        """
        Get the vendor's public key.

        Returns:
            VendorPublicKeyDTO with vendor's public key in DER base64 format
        """
        if self._http_client is not None:
            response = await self._http_client.get(
                f"{self.base_url}/vendor/keys/public"
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/vendor/keys/public")

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
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/payments",
                json=dto.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
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
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/closure-requests",
                json=dto.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
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
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
                json=dto.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
                    json=dto.model_dump(),
                )

        response.raise_for_status()
        return PaywordPaymentResponseDTO.model_validate(response.json())

    async def receive_payword_payment_raw(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> httpx.Response:
        """
        Submit a PayWord payment to the vendor without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
        if self._http_client is not None:
            return await self._http_client.post(
                f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
                json=dto.model_dump(),
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/vendor/channels/payword/{channel_id}/payments",
                json=dto.model_dump(),
            )

    async def request_channel_closure_payword(self, channel_id: str) -> None:
        """Request closure of a PayWord channel."""
        dto = CloseChannelDTO(computed_id=channel_id)
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/vendor/channels/payword/{channel_id}/closure-requests",
                json=dto.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/vendor/channels/payword/{channel_id}/closure-requests",
                    json=dto.model_dump(),
                )

        response.raise_for_status()
        assert response.status_code == 204

    async def receive_payment_raw(
        self, channel_id: str, payment_envelope: Envelope
    ) -> httpx.Response:
        """
        Submit a payment to the vendor without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = ReceivePaymentDTO(envelope=payment_envelope)
        if self._http_client is not None:
            return await self._http_client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/payments",
                json=dto.model_dump(),
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/payments",
                json=dto.model_dump(),
            )

    async def request_channel_closure_raw(self, channel_id: str) -> httpx.Response:
        """
        Request channel closure without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = CloseChannelDTO(computed_id=channel_id)
        if self._http_client is not None:
            return await self._http_client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/closure-requests",
                json=dto.model_dump(),
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/vendor/channels/signature/{channel_id}/closure-requests",
                json=dto.model_dump(),
            )
