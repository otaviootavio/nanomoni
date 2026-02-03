"""Test implementation of IssuerClientProtocol for unit testing."""

from __future__ import annotations

from typing import Optional, Type
from types import TracebackType

from nanomoni.application.issuer.dtos import (
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
from nanomoni.application.issuer.payword_dtos import (
    PaywordOpenChannelResponseDTO,
    PaywordPaymentChannelResponseDTO,
    PaywordSettlementRequestDTO,
)
from nanomoni.application.issuer.paytree_dtos import (
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
    PaytreeSettlementRequestDTO,
)


class TestIssuerClient:
    """Mock implementation of IssuerClientProtocol for testing.

    This client allows configuring responses for each method call,
    making it easy to test different scenarios without actual HTTP calls.
    """

    def __init__(self) -> None:
        # Call tracking
        self.calls: list[tuple[str, dict]] = []

        # Configurable responses
        self._register_response: Optional[RegistrationResponseDTO] = None
        self._public_key_response: Optional[IssuerPublicKeyDTO] = None
        self._open_channel_response: Optional[OpenChannelResponseDTO] = None
        self._get_channel_response: Optional[PaymentChannelResponseDTO] = None
        self._settle_channel_response: Optional[CloseChannelResponseDTO] = None

        # PayWord responses
        self._open_payword_channel_response: Optional[PaywordOpenChannelResponseDTO] = (
            None
        )
        self._get_payword_channel_response: Optional[
            PaywordPaymentChannelResponseDTO
        ] = None
        self._settle_payword_channel_response: Optional[CloseChannelResponseDTO] = None

        # PayTree responses
        self._open_paytree_channel_response: Optional[PaytreeOpenChannelResponseDTO] = (
            None
        )
        self._get_paytree_channel_response: Optional[
            PaytreePaymentChannelResponseDTO
        ] = None
        self._settle_paytree_channel_response: Optional[CloseChannelResponseDTO] = None

        # Error configuration
        self._should_raise: Optional[Exception] = None

    # Configuration methods

    def set_register_response(self, response: RegistrationResponseDTO) -> None:
        """Set the response for register() calls."""
        self._register_response = response

    def set_public_key_response(self, response: IssuerPublicKeyDTO) -> None:
        """Set the response for get_public_key() calls."""
        self._public_key_response = response

    def set_open_channel_response(self, response: OpenChannelResponseDTO) -> None:
        """Set the response for open_payment_channel() calls."""
        self._open_channel_response = response

    def set_get_channel_response(self, response: PaymentChannelResponseDTO) -> None:
        """Set the response for get_payment_channel() calls."""
        self._get_channel_response = response

    def set_settle_channel_response(self, response: CloseChannelResponseDTO) -> None:
        """Set the response for settle_payment_channel() calls."""
        self._settle_channel_response = response

    def set_open_payword_channel_response(
        self, response: PaywordOpenChannelResponseDTO
    ) -> None:
        """Set the response for open_payword_payment_channel() calls."""
        self._open_payword_channel_response = response

    def set_get_payword_channel_response(
        self, response: PaywordPaymentChannelResponseDTO
    ) -> None:
        """Set the response for get_payword_payment_channel() calls."""
        self._get_payword_channel_response = response

    def set_settle_payword_channel_response(
        self, response: CloseChannelResponseDTO
    ) -> None:
        """Set the response for settle_payword_payment_channel() calls."""
        self._settle_payword_channel_response = response

    def set_open_paytree_channel_response(
        self, response: PaytreeOpenChannelResponseDTO
    ) -> None:
        """Set the response for open_paytree_payment_channel() calls."""
        self._open_paytree_channel_response = response

    def set_get_paytree_channel_response(
        self, response: PaytreePaymentChannelResponseDTO
    ) -> None:
        """Set the response for get_paytree_payment_channel() calls."""
        self._get_paytree_channel_response = response

    def set_settle_paytree_channel_response(
        self, response: CloseChannelResponseDTO
    ) -> None:
        """Set the response for settle_paytree_payment_channel() calls."""
        self._settle_paytree_channel_response = response

    def set_error(self, error: Exception) -> None:
        """Configure the client to raise an error on the next call."""
        self._should_raise = error

    def clear_calls(self) -> None:
        """Clear the call history."""
        self.calls.clear()

    # Protocol implementation

    async def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        """Register a client account."""
        self.calls.append(("register", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._register_response is None:
            raise ValueError("register_response not configured")
        return self._register_response

    async def get_public_key(self) -> IssuerPublicKeyDTO:
        """Get the issuer's public key."""
        self.calls.append(("get_public_key", {}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._public_key_response is None:
            raise ValueError("public_key_response not configured")
        return self._public_key_response

    async def open_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> OpenChannelResponseDTO:
        """Open a signature-based payment channel."""
        self.calls.append(("open_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._open_channel_response is None:
            raise ValueError("open_channel_response not configured")
        return self._open_channel_response

    async def get_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        """Get a signature-based payment channel."""
        self.calls.append(("get_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._get_channel_response is None:
            raise ValueError("get_channel_response not configured")
        return self._get_channel_response

    async def settle_payment_channel(
        self,
        channel_id: str,
        dto: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a signature-based payment channel."""
        self.calls.append(
            ("settle_payment_channel", {"channel_id": channel_id, "dto": dto})
        )
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._settle_channel_response is None:
            raise ValueError("settle_channel_response not configured")
        return self._settle_channel_response

    async def open_payword_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaywordOpenChannelResponseDTO:
        """Open a PayWord payment channel."""
        self.calls.append(("open_payword_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._open_payword_channel_response is None:
            raise ValueError("open_payword_channel_response not configured")
        return self._open_payword_channel_response

    async def get_payword_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaywordPaymentChannelResponseDTO:
        """Get a PayWord payment channel."""
        self.calls.append(("get_payword_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._get_payword_channel_response is None:
            raise ValueError("get_payword_channel_response not configured")
        return self._get_payword_channel_response

    async def settle_payword_payment_channel(
        self,
        channel_id: str,
        dto: PaywordSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayWord payment channel."""
        self.calls.append(
            ("settle_payword_payment_channel", {"channel_id": channel_id, "dto": dto})
        )
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._settle_payword_channel_response is None:
            raise ValueError("settle_payword_channel_response not configured")
        return self._settle_payword_channel_response

    async def open_paytree_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        """Open a PayTree payment channel."""
        self.calls.append(("open_paytree_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._open_paytree_channel_response is None:
            raise ValueError("open_paytree_channel_response not configured")
        return self._open_paytree_channel_response

    async def get_paytree_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreePaymentChannelResponseDTO:
        """Get a PayTree payment channel."""
        self.calls.append(("get_paytree_payment_channel", {"dto": dto}))
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._get_paytree_channel_response is None:
            raise ValueError("get_paytree_channel_response not configured")
        return self._get_paytree_channel_response

    async def settle_paytree_payment_channel(
        self,
        channel_id: str,
        dto: PaytreeSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayTree payment channel."""
        self.calls.append(
            ("settle_paytree_payment_channel", {"channel_id": channel_id, "dto": dto})
        )
        if self._should_raise:
            error = self._should_raise
            self._should_raise = None
            raise error
        if self._settle_paytree_channel_response is None:
            raise ValueError("settle_paytree_channel_response not configured")
        return self._settle_paytree_channel_response

    async def aclose(self) -> None:
        """Close the client (no-op for test client)."""
        pass

    async def __aenter__(self) -> "TestIssuerClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit."""
        pass
