"""Protocol interface for issuer client implementations.

This protocol defines the contract that all issuer client implementations must satisfy.
It enables dependency injection and makes services testable by allowing mock implementations.
"""

from __future__ import annotations

from typing import Protocol, Type, Optional, Callable, TYPE_CHECKING
from types import TracebackType

if TYPE_CHECKING:
    # Avoid circular imports by only importing types during type checking
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
    from ...application.issuer.payword_dtos import (
        PaywordOpenChannelResponseDTO,
        PaywordPaymentChannelResponseDTO,
        PaywordSettlementRequestDTO,
    )
    from ...application.issuer.paytree_dtos import (
        PaytreeOpenChannelResponseDTO,
        PaytreePaymentChannelResponseDTO,
        PaytreeSettlementRequestDTO,
    )


class IssuerClientProtocol(Protocol):
    """Protocol defining the interface for issuer client implementations.

    This protocol enables dependency injection by allowing services to accept
    any implementation that satisfies this interface, rather than being tightly
    coupled to a specific concrete class.

    Implementations should provide async methods for:
    - Account registration and public key retrieval
    - Payment channel operations (open, get, settle) for signature, PayWord, and PayTree modes
    - Context manager support for resource cleanup
    """

    # Registration & Keys

    async def register(
        self, dto: "RegistrationRequestDTO"
    ) -> "RegistrationResponseDTO":
        """Register a client account with the issuer.

        Args:
            dto: Registration request containing client public key

        Returns:
            Registration response with client public key and initial balance
        """
        ...

    async def get_public_key(self) -> "IssuerPublicKeyDTO":
        """Get the issuer's public key.

        Returns:
            Issuer public key in DER base64 format
        """
        ...

    # Signature Payment Channels

    async def open_payment_channel(
        self, dto: "OpenChannelRequestDTO"
    ) -> "OpenChannelResponseDTO":
        """Open a signature-based payment channel.

        Args:
            dto: Open channel request with client-signed envelope

        Returns:
            Open channel response with channel details
        """
        ...

    async def get_payment_channel(
        self, dto: "GetPaymentChannelRequestDTO"
    ) -> "PaymentChannelResponseDTO":
        """Get a signature-based payment channel by ID.

        Args:
            dto: Get channel request with channel ID

        Returns:
            Payment channel response with full channel details
        """
        ...

    async def settle_payment_channel(
        self,
        channel_id: str,
        dto: "CloseChannelRequestDTO",
    ) -> "CloseChannelResponseDTO":
        """Settle a signature-based payment channel.

        Args:
            channel_id: ID of the channel to settle
            dto: Close channel request with client and vendor signatures

        Returns:
            Close channel response with updated balances
        """
        ...

    # PayWord Payment Channels

    async def open_payword_payment_channel(
        self, dto: "OpenChannelRequestDTO"
    ) -> "PaywordOpenChannelResponseDTO":
        """Open a PayWord (hash-chain) payment channel.

        Args:
            dto: Open channel request with client-signed envelope

        Returns:
            PayWord open channel response with channel and PayWord commitment details
        """
        ...

    async def get_payword_payment_channel(
        self, dto: "GetPaymentChannelRequestDTO"
    ) -> "PaywordPaymentChannelResponseDTO":
        """Get a PayWord payment channel by ID.

        Args:
            dto: Get channel request with channel ID

        Returns:
            PayWord payment channel response with full channel and PayWord details
        """
        ...

    async def settle_payword_payment_channel(
        self,
        channel_id: str,
        dto: "PaywordSettlementRequestDTO",
    ) -> "CloseChannelResponseDTO":
        """Settle a PayWord payment channel.

        Args:
            channel_id: ID of the channel to settle
            dto: PayWord settlement request with token and vendor signature

        Returns:
            Close channel response with updated balances
        """
        ...

    # PayTree Payment Channels

    async def open_paytree_payment_channel(
        self, dto: "OpenChannelRequestDTO"
    ) -> "PaytreeOpenChannelResponseDTO":
        """Open a PayTree (Merkle tree) payment channel.

        Args:
            dto: Open channel request with client-signed envelope

        Returns:
            PayTree open channel response with channel and PayTree commitment details
        """
        ...

    async def get_paytree_payment_channel(
        self, dto: "GetPaymentChannelRequestDTO"
    ) -> "PaytreePaymentChannelResponseDTO":
        """Get a PayTree payment channel by ID.

        Args:
            dto: Get channel request with channel ID

        Returns:
            PayTree payment channel response with full channel and PayTree details
        """
        ...

    async def settle_paytree_payment_channel(
        self,
        channel_id: str,
        dto: "PaytreeSettlementRequestDTO",
    ) -> "CloseChannelResponseDTO":
        """Settle a PayTree payment channel.

        Args:
            channel_id: ID of the channel to settle
            dto: PayTree settlement request with leaf, siblings, and vendor signature

        Returns:
            Close channel response with updated balances
        """
        ...

    # Context Manager Support

    async def aclose(self) -> None:
        """Close the client and release resources.

        This method should be called when done using the client, or use
        the async context manager protocol (async with).
        """
        ...

    async def __aenter__(self: "IssuerClientProtocol") -> "IssuerClientProtocol":
        """Async context manager entry.

        Returns:
            Self for use in async with statements
        """
        ...

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        ...


# Factory type for creating issuer clients
# This allows dependency injection while maintaining the context manager pattern
IssuerClientFactory = Callable[[], IssuerClientProtocol]
