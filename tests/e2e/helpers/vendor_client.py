"""VendorTestClient wraps vendor API operations for E2E tests."""

from __future__ import annotations

import httpx

from nanomoni.application.vendor.dtos import (
    VendorPublicKeyDTO,
    ReceivePaymentDTO,
    CloseChannelDTO,
    OffChainTxResponseDTO,
)
from nanomoni.crypto.certificates import Envelope


class VendorTestClient:
    """HTTP client for interacting with the Vendor API in E2E tests."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """
        Initialize the vendor test client.

        Args:
            base_url: Base URL of the vendor API
            timeout: Request timeout in seconds
        """
        if not base_url:
            raise ValueError("VendorTestClient requires a non-empty base_url.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_public_key(self) -> VendorPublicKeyDTO:
        """
        Get the vendor's public key.

        Returns:
            VendorPublicKeyDTO with vendor's public key in DER base64 format
        """
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/vendor/channels/{channel_id}/payments",
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/vendor/channels/{channel_id}/closure-requests",
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/vendor/channels/{channel_id}/payments",
                json=dto.model_dump(),
            )

    async def request_channel_closure_raw(self, channel_id: str) -> httpx.Response:
        """
        Request channel closure without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        dto = CloseChannelDTO(computed_id=channel_id)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/vendor/channels/{channel_id}/closure-requests",
                json=dto.model_dump(),
            )
