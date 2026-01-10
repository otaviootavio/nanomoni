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


class IssuerTestClient:
    """HTTP client for interacting with the Issuer API in E2E tests."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """
        Initialize the issuer test client.

        Args:
            base_url: Base URL of the issuer API
            timeout: Request timeout in seconds
        """
        if not base_url:
            raise ValueError("IssuerTestClient requires a non-empty base_url.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/issuer/channels",
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/issuer/channels/{computed_id}"
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/issuer/channels/{computed_id}/settlements",
                json=close_request.model_dump(),
            )
            response.raise_for_status()
            return CloseChannelResponseDTO.model_validate(response.json())
