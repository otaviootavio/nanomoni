"""Adapter that wraps issuer use cases for testing (similar to IssuerTestClient but calls use cases directly)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import TracebackType

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    IssuerPublicKeyDTO,
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    PaymentChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
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
from nanomoni.application.issuer.paytree_first_opt_dtos import (
    PaytreeFirstOptOpenChannelResponseDTO,
    PaytreeFirstOptPaymentChannelResponseDTO,
    PaytreeFirstOptSettlementRequestDTO,
)
from nanomoni.application.issuer.paytree_second_opt_dtos import (
    PaytreeSecondOptOpenChannelResponseDTO,
    PaytreeSecondOptPaymentChannelResponseDTO,
    PaytreeSecondOptSettlementRequestDTO,
)
from nanomoni.application.issuer.use_cases.registration import RegistrationService
from nanomoni.application.issuer.use_cases.payment_channel import PaymentChannelService
from nanomoni.application.issuer.use_cases.payword_channel import PaywordChannelService
from nanomoni.application.issuer.use_cases.paytree_channel import PaytreeChannelService
from nanomoni.application.issuer.use_cases.paytree_first_opt_channel import (
    PaytreeFirstOptChannelService,
)
from nanomoni.application.issuer.use_cases.paytree_second_opt_channel import (
    PaytreeSecondOptChannelService,
)


@dataclass(frozen=True)
class UseCaseResponse:
    """Response wrapper for use case error testing (similar to AiohttpResponse)."""

    status_code: int
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.content:
            return None
        return json.loads(self.text)


class UseCaseIssuerClient:
    """Adapter that implements IssuerClientProtocol by calling issuer use cases directly.

    This allows vendor services to call issuer functionality without HTTP,
    making tests fast and isolated.
    """

    def __init__(
        self,
        registration_service: RegistrationService,
        payment_channel_service: PaymentChannelService,
        payword_channel_service: PaywordChannelService,
        paytree_channel_service: PaytreeChannelService,
        paytree_first_opt_channel_service: PaytreeFirstOptChannelService,
        paytree_second_opt_channel_service: PaytreeSecondOptChannelService,
    ) -> None:
        self.registration_service = registration_service
        self.payment_channel_service = payment_channel_service
        self.payword_channel_service = payword_channel_service
        self.paytree_channel_service = paytree_channel_service
        self.paytree_first_opt_channel_service = paytree_first_opt_channel_service
        self.paytree_second_opt_channel_service = paytree_second_opt_channel_service

    async def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        """Register a client account with the issuer (protocol method)."""
        return await self.registration_service.register(dto)

    async def register_account(
        self, public_key_der_b64: str
    ) -> RegistrationResponseDTO:
        """Register an account (client or vendor) with the issuer."""
        dto = RegistrationRequestDTO(client_public_key_der_b64=public_key_der_b64)
        return await self.registration_service.register(dto)

    async def get_account(self, public_key_der_b64: str) -> RegistrationResponseDTO:
        """Fetch an existing issuer account by public key."""
        return await self.registration_service.get_account(public_key_der_b64)

    async def get_public_key(self) -> IssuerPublicKeyDTO:
        """Get the issuer's public key."""
        return self.registration_service.get_issuer_public_key()

    async def open_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> OpenChannelResponseDTO:
        """Open a signature-based payment channel (protocol method)."""
        return await self.payment_channel_service.open_channel(dto)

    async def open_channel(self, dto: OpenChannelRequestDTO) -> OpenChannelResponseDTO:
        """Open a signature-based payment channel."""
        return await self.payment_channel_service.open_channel(dto)

    async def get_channel(self, channel_id: str) -> PaymentChannelResponseDTO:
        """Get a signature-based payment channel."""
        from nanomoni.application.issuer.dtos import GetPaymentChannelRequestDTO

        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.payment_channel_service.get_channel(dto)

    async def get_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        """Get a signature-based payment channel (protocol method)."""
        return await self.payment_channel_service.get_channel(dto)

    async def settle_payment_channel(
        self,
        channel_id: str,
        dto: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a signature-based payment channel (protocol method)."""
        # PaymentChannelService.settle_channel takes only dto, channel_id is in the dto
        return await self.payment_channel_service.settle_channel(dto)

    async def close_channel(
        self,
        channel_id: str,
        dto: CloseChannelRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a signature-based payment channel."""
        # PaymentChannelService.settle_channel takes only dto, channel_id is in the dto
        return await self.payment_channel_service.settle_channel(dto)

    async def open_payword_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaywordOpenChannelResponseDTO:
        """Open a PayWord payment channel (protocol method)."""
        return await self.payword_channel_service.open_channel(dto)

    async def open_payword_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaywordOpenChannelResponseDTO:
        """Open a PayWord payment channel."""
        return await self.payword_channel_service.open_channel(dto)

    async def get_payword_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaywordPaymentChannelResponseDTO:
        """Get a PayWord payment channel (protocol method)."""
        return await self.payword_channel_service.get_channel(dto)

    async def get_payword_channel(
        self, channel_id: str
    ) -> PaywordPaymentChannelResponseDTO:
        """Get a PayWord payment channel."""
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.payword_channel_service.get_channel(dto)

    async def settle_payword_payment_channel(
        self,
        channel_id: str,
        dto: PaywordSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayWord payment channel (protocol method)."""
        return await self.payword_channel_service.settle_channel(channel_id, dto)

    async def open_paytree_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        """Open a PayTree payment channel (protocol method)."""
        return await self.paytree_channel_service.open_channel(dto)

    async def open_paytree_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        """Open a PayTree payment channel."""
        return await self.paytree_channel_service.open_channel(dto)

    async def get_paytree_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreePaymentChannelResponseDTO:
        """Get a PayTree payment channel (protocol method)."""
        return await self.paytree_channel_service.get_channel(dto)

    async def get_paytree_channel(
        self, channel_id: str
    ) -> PaytreePaymentChannelResponseDTO:
        """Get a PayTree payment channel."""
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.paytree_channel_service.get_channel(dto)

    async def settle_paytree_payment_channel(
        self,
        channel_id: str,
        dto: PaytreeSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayTree payment channel (protocol method)."""
        return await self.paytree_channel_service.settle_channel(channel_id, dto)

    async def open_paytree_first_opt_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeFirstOptOpenChannelResponseDTO:
        """Open a PayTree First Opt payment channel (protocol method)."""
        return await self.paytree_first_opt_channel_service.open_channel(dto)

    async def get_paytree_first_opt_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreeFirstOptPaymentChannelResponseDTO:
        """Get a PayTree First Opt payment channel (protocol method)."""
        return await self.paytree_first_opt_channel_service.get_channel(dto)

    async def settle_paytree_first_opt_payment_channel(
        self,
        channel_id: str,
        dto: PaytreeFirstOptSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayTree First Opt payment channel (protocol method)."""
        return await self.paytree_first_opt_channel_service.settle_channel(
            channel_id, dto
        )

    async def open_paytree_first_opt_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeFirstOptOpenChannelResponseDTO:
        """Open a PayTree First Opt payment channel."""
        return await self.paytree_first_opt_channel_service.open_channel(dto)

    async def get_paytree_first_opt_channel(
        self, channel_id: str
    ) -> PaytreeFirstOptPaymentChannelResponseDTO:
        """Get a PayTree First Opt payment channel."""
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.paytree_first_opt_channel_service.get_channel(dto)

    async def open_paytree_second_opt_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeSecondOptOpenChannelResponseDTO:
        """Open a PayTree Second Opt payment channel (protocol method)."""
        return await self.paytree_second_opt_channel_service.open_channel(dto)

    async def get_paytree_second_opt_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreeSecondOptPaymentChannelResponseDTO:
        """Get a PayTree Second Opt payment channel (protocol method)."""
        return await self.paytree_second_opt_channel_service.get_channel(dto)

    async def settle_paytree_second_opt_payment_channel(
        self,
        channel_id: str,
        dto: PaytreeSecondOptSettlementRequestDTO,
    ) -> CloseChannelResponseDTO:
        """Settle a PayTree Second Opt payment channel (protocol method)."""
        return await self.paytree_second_opt_channel_service.settle_channel(
            channel_id, dto
        )

    async def open_paytree_second_opt_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeSecondOptOpenChannelResponseDTO:
        """Open a PayTree Second Opt payment channel."""
        return await self.paytree_second_opt_channel_service.open_channel(dto)

    async def get_paytree_second_opt_channel(
        self, channel_id: str
    ) -> PaytreeSecondOptPaymentChannelResponseDTO:
        """Get a PayTree Second Opt payment channel."""
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.paytree_second_opt_channel_service.get_channel(dto)

    async def aclose(self) -> None:
        """Close the client (no-op for in-process adapter)."""
        pass

    async def __aenter__(self) -> "UseCaseIssuerClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        pass

    async def open_channel_raw(self, dto: OpenChannelRequestDTO) -> UseCaseResponse:
        """
        Open a signature-based payment channel without raising on error.

        Returns a response object for error case testing.
        """
        try:
            result = await self.payment_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def open_payword_channel_raw(
        self, dto: OpenChannelRequestDTO
    ) -> UseCaseResponse:
        """
        Open a PayWord payment channel without raising on error.

        Returns a response object for error case testing.
        """
        try:
            result = await self.payword_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def open_paytree_channel_raw(
        self, dto: OpenChannelRequestDTO
    ) -> UseCaseResponse:
        """
        Open a PayTree payment channel without raising on error.

        Returns a response object for error case testing.
        """
        try:
            result = await self.paytree_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )
