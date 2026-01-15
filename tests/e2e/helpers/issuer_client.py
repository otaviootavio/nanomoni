"""IssuerTestClient wraps issuer API operations for E2E tests."""

from __future__ import annotations

import httpx

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


class IssuerTestClient:
    """HTTP client for interacting with the Issuer API in E2E tests."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        http_client: httpx.AsyncClient | None = None,
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
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/issuer/accounts",
                json=dto.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
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
            OpenChannelResponseDTO with channel details including computed_id
        """
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/issuer/channels/signature",
                json=open_channel_request.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/issuer/channels/signature",
                    json=open_channel_request.model_dump(),
                )

        response.raise_for_status()
        return OpenChannelResponseDTO.model_validate(response.json())

    async def get_channel(self, computed_id: str) -> PaymentChannelResponseDTO:
        """
        Get payment channel state by computed ID.

        Args:
            computed_id: Channel's computed ID

        Returns:
            PaymentChannelResponseDTO with channel state
        """
        if self._http_client is not None:
            response = await self._http_client.get(
                f"{self.base_url}/issuer/channels/signature/{computed_id}"
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/issuer/channels/signature/{computed_id}"
                )

        response.raise_for_status()
        return PaymentChannelResponseDTO.model_validate(response.json())

    async def close_channel(
        self,
        computed_id: str,
        close_request: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        """
        Close and settle a payment channel.

        Args:
            computed_id: Channel's computed ID
            close_request: Close channel request with signatures

        Returns:
            CloseChannelResponseDTO with final balances
        """
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/issuer/channels/signature/{computed_id}/settlements",
                json=close_request.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/issuer/channels/signature/{computed_id}/settlements",
                    json=close_request.model_dump(),
                )

        response.raise_for_status()
        return CloseChannelResponseDTO.model_validate(response.json())

    async def open_payword_channel(
        self,
        open_channel_request: OpenChannelRequestDTO,
    ) -> PaywordOpenChannelResponseDTO:
        """Open a PayWord-enabled payment channel."""
        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/issuer/channels/payword",
                json=open_channel_request.model_dump(),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/issuer/channels/payword",
                    json=open_channel_request.model_dump(),
                )

        response.raise_for_status()
        return PaywordOpenChannelResponseDTO.model_validate(response.json())

    async def get_payword_channel(
        self, computed_id: str
    ) -> PaywordPaymentChannelResponseDTO:
        """Get PayWord payment channel state by computed ID."""
        if self._http_client is not None:
            response = await self._http_client.get(
                f"{self.base_url}/issuer/channels/payword/{computed_id}"
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/issuer/channels/payword/{computed_id}"
                )

        response.raise_for_status()
        return PaywordPaymentChannelResponseDTO.model_validate(response.json())
