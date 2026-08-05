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
    PaytreeChildPairSettlementRequestDTO,
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
    PaytreeSettlementRequestDTO,
)
from nanomoni.application.issuer.use_cases.registration import RegistrationService
from nanomoni.application.issuer.use_cases.payment_channel import PaymentChannelService
from nanomoni.application.issuer.use_cases.payword_channel import PaywordChannelService
from nanomoni.application.issuer.use_cases.paytree_channel import PaytreeChannelService


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
    """Adapter that implements IssuerClientProtocol by calling issuer use cases directly."""

    def __init__(
        self,
        registration_service: RegistrationService,
        payment_channel_service: PaymentChannelService,
        payword_channel_service: PaywordChannelService,
        paytree_std_channel_service: PaytreeChannelService,
        paytree_first_opt_channel_service: PaytreeChannelService,
        paytree_child_pair_channel_service: PaytreeChannelService | None = None,
    ) -> None:
        self.registration_service = registration_service
        self.payment_channel_service = payment_channel_service
        self.payword_channel_service = payword_channel_service
        self.paytree_std_channel_service = paytree_std_channel_service
        self.paytree_first_opt_channel_service = paytree_first_opt_channel_service
        self.paytree_child_pair_channel_service = (
            paytree_child_pair_channel_service or paytree_std_channel_service
        )

    async def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        return await self.registration_service.register(dto)

    async def register_account(
        self, public_key_der_b64: str
    ) -> RegistrationResponseDTO:
        dto = RegistrationRequestDTO(client_public_key_der_b64=public_key_der_b64)
        return await self.registration_service.register(dto)

    async def get_account(self, public_key_der_b64: str) -> RegistrationResponseDTO:
        return await self.registration_service.get_account(public_key_der_b64)

    async def get_public_key(self) -> IssuerPublicKeyDTO:
        return self.registration_service.get_issuer_public_key()

    async def open_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> OpenChannelResponseDTO:
        return await self.payment_channel_service.open_channel(dto)

    async def open_channel(self, dto: OpenChannelRequestDTO) -> OpenChannelResponseDTO:
        return await self.payment_channel_service.open_channel(dto)

    async def get_channel(self, channel_id: str) -> PaymentChannelResponseDTO:
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.payment_channel_service.get_channel(dto)

    async def get_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        return await self.payment_channel_service.get_channel(dto)

    async def settle_payment_channel(
        self, channel_id: str, dto: CloseChannelRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.payment_channel_service.settle_channel(dto)

    async def close_channel(
        self, channel_id: str, dto: CloseChannelRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.payment_channel_service.settle_channel(dto)

    # PayWord

    async def open_payword_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaywordOpenChannelResponseDTO:
        return await self.payword_channel_service.open_channel(dto)

    async def open_payword_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaywordOpenChannelResponseDTO:
        return await self.payword_channel_service.open_channel(dto)

    async def get_payword_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaywordPaymentChannelResponseDTO:
        return await self.payword_channel_service.get_channel(dto)

    async def get_payword_channel(
        self, channel_id: str
    ) -> PaywordPaymentChannelResponseDTO:
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.payword_channel_service.get_channel(dto)

    async def settle_payword_payment_channel(
        self, channel_id: str, dto: PaywordSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.payword_channel_service.settle_channel(channel_id, dto)

    # PayTree Std

    async def open_paytree_std_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_std_channel_service.open_channel(dto)

    async def open_paytree_std_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_std_channel_service.open_channel(dto)

    async def get_paytree_std_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreePaymentChannelResponseDTO:
        return await self.paytree_std_channel_service.get_channel(dto)

    async def settle_paytree_std_payment_channel(
        self, channel_id: str, dto: PaytreeSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.paytree_std_channel_service.settle_channel(channel_id, dto)

    # PayTree First-Opt

    async def open_paytree_first_opt_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_first_opt_channel_service.open_channel(dto)

    async def open_paytree_first_opt_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_first_opt_channel_service.open_channel(dto)

    async def get_paytree_first_opt_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreePaymentChannelResponseDTO:
        return await self.paytree_first_opt_channel_service.get_channel(dto)

    async def settle_paytree_first_opt_payment_channel(
        self, channel_id: str, dto: PaytreeSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.paytree_first_opt_channel_service.settle_channel(
            channel_id, dto
        )

    # PayTree Child-Pair

    async def open_paytree_child_pair_payment_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_child_pair_channel_service.open_channel(dto)

    async def open_paytree_child_pair_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
        return await self.paytree_child_pair_channel_service.open_channel(dto)

    async def get_paytree_child_pair_payment_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaytreePaymentChannelResponseDTO:
        return await self.paytree_child_pair_channel_service.get_channel(dto)

    async def settle_paytree_child_pair_payment_channel(
        self, channel_id: str, dto: PaytreeChildPairSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        return await self.paytree_child_pair_channel_service.settle_channel_child_pair(
            channel_id, dto
        )

    # Convenience GET (reads from shared repo; either service works)

    async def get_paytree_channel(
        self, channel_id: str
    ) -> PaytreePaymentChannelResponseDTO:
        dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        return await self.paytree_std_channel_service.get_channel(dto)

    # Context manager

    async def aclose(self) -> None:
        pass

    async def __aenter__(self) -> "UseCaseIssuerClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: "TracebackType | None",
    ) -> None:
        pass

    # Raw error-return helpers

    async def open_channel_raw(self, dto: OpenChannelRequestDTO) -> UseCaseResponse:
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
        try:
            result = await self.payword_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def open_paytree_std_channel_raw(
        self, dto: OpenChannelRequestDTO
    ) -> UseCaseResponse:
        try:
            result = await self.paytree_std_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def open_paytree_first_opt_channel_raw(
        self, dto: OpenChannelRequestDTO
    ) -> UseCaseResponse:
        try:
            result = await self.paytree_first_opt_channel_service.open_channel(dto)
            return UseCaseResponse(
                status_code=201, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )
