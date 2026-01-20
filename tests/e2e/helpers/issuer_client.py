"""IssuerTestClient wraps issuer API operations for E2E tests."""

from __future__ import annotations

import aiohttp

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    PaymentChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
)
from nanomoni.application.issuer.payword_dtos import (
    PaywordOpenChannelResponseDTO,
    PaywordPaymentChannelResponseDTO,
)
from nanomoni.application.issuer.paytree_dtos import (
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
)

from tests.e2e.helpers.http import AiohttpResponse


class IssuerTestClient:
    """HTTP client for interacting with the Issuer API in E2E tests."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        http_client: aiohttp.ClientSession | None = None,
    ) -> None:
        """
        Initialize the issuer test client.

        Args:
            base_url: Base URL of the issuer API
            timeout: Request timeout in seconds
            http_client: Optional shared AsyncClient (reuses connections / keep-alive)
        """
        if not base_url:
            raise ValueError("IssuerTestClient requires a non-empty base_url.")
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

    async def register_account(
        self, public_key_der_b64: str
    ) -> RegistrationResponseDTO:
        """
        Register an account (client or vendor) with the issuer.

        Args:
            public_key_der_b64: Public key of the account to register

        Returns:
            RegistrationResponseDTO with account balance
        """
        dto = RegistrationRequestDTO(client_public_key_der_b64=public_key_der_b64)
        response = await self._request(
            "POST",
            f"{self.base_url}/issuer/accounts",
            json=dto.model_dump(),
        )

        response.raise_for_status()
        return RegistrationResponseDTO.model_validate(response.json())

    async def open_channel(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> OpenChannelResponseDTO:
        """
        Open a payment channel.

        Args:
            open_channel_request: Pre-signed open channel request

        Returns:
            OpenChannelResponseDTO with channel details including channel_id
        """
        response = await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/signature",
            json=open_channel_request.model_dump(),
        )

        response.raise_for_status()
        return OpenChannelResponseDTO.model_validate(response.json())

    async def open_channel_raw(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> AiohttpResponse:
        """
        Open a payment channel without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        return await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/signature",
            json=open_channel_request.model_dump(),
        )

    async def get_channel(self, channel_id: str) -> PaymentChannelResponseDTO:
        """
        Get payment channel state by channel ID.

        Args:
            channel_id: Channel ID for the payment channel to fetch

        Returns:
            PaymentChannelResponseDTO with channel state
        """
        response = await self._request(
            "GET",
            f"{self.base_url}/issuer/channels/signature/{channel_id}",
        )

        response.raise_for_status()
        return PaymentChannelResponseDTO.model_validate(response.json())

    async def settle_channel(
        self,
        channel_id: str,
        close_request: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        """
        Close and settle a payment channel.

        Args:
            channel_id: Channel ID for the payment channel to close
            close_request: Close channel request with signatures

        Returns:
            CloseChannelResponseDTO with final balances
        """
        response = await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/signature/{channel_id}/settlements",
            json=close_request.model_dump(),
        )

        response.raise_for_status()
        return CloseChannelResponseDTO.model_validate(response.json())

    async def open_payword_channel(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> PaywordOpenChannelResponseDTO:
        """Open a PayWord-enabled payment channel."""
        response = await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/payword",
            json=open_channel_request.model_dump(),
        )

        response.raise_for_status()
        return PaywordOpenChannelResponseDTO.model_validate(response.json())

    async def open_payword_channel_raw(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> AiohttpResponse:
        """
        Open a PayWord-enabled payment channel without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        return await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/payword",
            json=open_channel_request.model_dump(),
        )

    async def get_payword_channel(
        self, channel_id: str
    ) -> PaywordPaymentChannelResponseDTO:
        """Get PayWord payment channel state by computed ID."""
        response = await self._request(
            "GET",
            f"{self.base_url}/issuer/channels/payword/{channel_id}",
        )

        response.raise_for_status()
        return PaywordPaymentChannelResponseDTO.model_validate(response.json())

    async def open_paytree_channel(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> PaytreeOpenChannelResponseDTO:
        """Open a PayTree-enabled payment channel."""
        response = await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/paytree",
            json=open_channel_request.model_dump(),
        )

        response.raise_for_status()
        return PaytreeOpenChannelResponseDTO.model_validate(response.json())

    async def open_paytree_channel_raw(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> AiohttpResponse:
        """
        Open a PayTree-enabled payment channel without raising on error status.

        Returns the raw HTTP response for error case testing.
        """
        return await self._request(
            "POST",
            f"{self.base_url}/issuer/channels/paytree",
            json=open_channel_request.model_dump(),
        )

    async def get_paytree_channel(
        self, channel_id: str
    ) -> PaytreePaymentChannelResponseDTO:
        """Get PayTree payment channel state by computed ID."""
        response = await self._request(
            "GET",
            f"{self.base_url}/issuer/channels/paytree/{channel_id}",
        )

        response.raise_for_status()
        return PaytreePaymentChannelResponseDTO.model_validate(response.json())
