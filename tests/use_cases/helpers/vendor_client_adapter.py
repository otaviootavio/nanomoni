"""Adapter that wraps vendor use cases for testing (similar to VendorTestClient but calls use cases directly)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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
from nanomoni.application.vendor.paytree_first_opt_dtos import (
    ReceivePaytreeFirstOptPaymentDTO,
    PaytreeFirstOptPaymentResponseDTO,
)
from nanomoni.application.vendor.paytree_second_opt_dtos import (
    ReceivePaytreeSecondOptPaymentDTO,
    PaytreeSecondOptPaymentResponseDTO,
)
from cryptography.exceptions import InvalidSignature

from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.application.vendor.use_cases.payword_payment import PaywordPaymentService
from nanomoni.application.vendor.use_cases.paytree_payment import PaytreePaymentService
from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)
from nanomoni.application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
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


class UseCaseVendorClient:
    """Adapter that wraps vendor use cases for testing.

    Provides a similar interface to VendorTestClient but calls use cases directly
    instead of making HTTP requests.
    """

    def __init__(
        self,
        payment_service: PaymentService,
        payword_payment_service: PaywordPaymentService,
        paytree_payment_service: PaytreePaymentService,
        paytree_first_opt_payment_service: PaytreeFirstOptPaymentService,
        paytree_second_opt_payment_service: PaytreeSecondOptPaymentService,
        vendor_public_key_der_b64: str,
    ) -> None:
        self.payment_service = payment_service
        self.payword_payment_service = payword_payment_service
        self.paytree_payment_service = paytree_payment_service
        self.paytree_first_opt_payment_service = paytree_first_opt_payment_service
        self.paytree_second_opt_payment_service = paytree_second_opt_payment_service
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64

    async def get_public_key(self) -> VendorPublicKeyDTO:
        """Get the vendor's public key."""
        return VendorPublicKeyDTO(public_key_der_b64=self.vendor_public_key_der_b64)

    async def receive_payment(
        self, channel_id: str, payment_dto: ReceivePaymentDTO
    ) -> OffChainTxResponseDTO:
        """Submit a payment to the vendor."""
        return await self.payment_service.receive_payment(payment_dto)

    async def request_channel_settlement(self, channel_id: str) -> None:
        """Request closure of a payment channel."""
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.payment_service.settle_channel(dto)

    async def receive_payword_payment(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> PaywordPaymentResponseDTO:
        """Submit a PayWord payment to the vendor."""
        dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
        return await self.payword_payment_service.receive_payword_payment(
            channel_id, dto
        )

    async def request_channel_settlement_payword(self, channel_id: str) -> None:
        """Request closure of a PayWord channel."""
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.payword_payment_service.settle_channel(channel_id, dto)

    async def receive_paytree_payment(
        self, channel_id: str, *, i: int, leaf_b64: str, siblings_b64: list[str]
    ) -> PaytreePaymentResponseDTO:
        """Submit a PayTree payment to the vendor."""
        dto = ReceivePaytreePaymentDTO(
            i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        return await self.paytree_payment_service.receive_paytree_payment(
            channel_id, dto
        )

    async def request_channel_settlement_paytree(self, channel_id: str) -> None:
        """Request closure of a PayTree channel."""
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.paytree_payment_service.settle_channel(dto)

    async def receive_paytree_first_opt_payment(
        self,
        channel_id: str,
        *,
        i: int,
        max_i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> PaytreeFirstOptPaymentResponseDTO:
        """Submit a PayTree First Opt payment to the vendor."""
        dto = ReceivePaytreeFirstOptPaymentDTO(
            i=i, max_i=max_i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        return await self.paytree_first_opt_payment_service.receive_payment(
            channel_id, dto
        )

    async def request_channel_settlement_paytree_first_opt(
        self, channel_id: str
    ) -> None:
        """Request closure of a PayTree First Opt channel."""
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.paytree_first_opt_payment_service.settle_channel(dto)

    async def receive_paytree_second_opt_payment(
        self,
        channel_id: str,
        *,
        i: int,
        max_i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> PaytreeSecondOptPaymentResponseDTO:
        """Submit a PayTree Second Opt payment to the vendor."""
        dto = ReceivePaytreeSecondOptPaymentDTO(
            i=i, max_i=max_i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        return await self.paytree_second_opt_payment_service.receive_payment(
            channel_id, dto
        )

    async def request_channel_settlement_paytree_second_opt(
        self, channel_id: str
    ) -> None:
        """Request closure of a PayTree Second Opt channel."""
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.paytree_second_opt_payment_service.settle_channel(dto)

    async def receive_payment_raw(
        self, channel_id: str, payment_dto: ReceivePaymentDTO
    ) -> UseCaseResponse:
        """
        Submit a payment to the vendor without raising on error.

        Returns a response object for error case testing.
        """
        try:
            result = await self.payment_service.receive_payment(payment_dto)
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except (ValueError, InvalidSignature) as e:
            error_msg = str(e)
            if isinstance(e, InvalidSignature):
                error_msg = "Invalid signature"
            return UseCaseResponse(
                status_code=400,
                content=json.dumps({"detail": error_msg}).encode("utf-8"),
            )

    async def receive_payword_payment_raw(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> UseCaseResponse:
        """
        Submit a PayWord payment to the vendor without raising on error.

        Returns a response object for error case testing.
        """
        try:
            dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
            result = await self.payword_payment_service.receive_payword_payment(
                channel_id, dto
            )
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def receive_paytree_payment_raw(
        self, channel_id: str, *, i: int, leaf_b64: str, siblings_b64: list[str]
    ) -> UseCaseResponse:
        """
        Submit a PayTree payment to the vendor without raising on error.

        Returns a response object for error case testing.
        """
        try:
            dto = ReceivePaytreePaymentDTO(
                i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
            )
            result = await self.paytree_payment_service.receive_paytree_payment(
                channel_id, dto
            )
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def receive_paytree_first_opt_payment_raw(
        self,
        channel_id: str,
        *,
        i: int,
        max_i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> UseCaseResponse:
        """
        Submit a PayTree First Opt payment to the vendor without raising on error.

        Returns a response object for error case testing.
        """
        try:
            dto = ReceivePaytreeFirstOptPaymentDTO(
                i=i, max_i=max_i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
            )
            result = await self.paytree_first_opt_payment_service.receive_payment(
                channel_id, dto
            )
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def receive_paytree_second_opt_payment_raw(
        self,
        channel_id: str,
        *,
        i: int,
        max_i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> UseCaseResponse:
        """
        Submit a PayTree Second Opt payment to the vendor without raising on error.

        Returns a response object for error case testing.
        """
        try:
            dto = ReceivePaytreeSecondOptPaymentDTO(
                i=i, max_i=max_i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
            )
            result = await self.paytree_second_opt_payment_service.receive_payment(
                channel_id, dto
            )
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    async def request_channel_settlement_raw(self, channel_id: str) -> UseCaseResponse:
        """
        Request channel closure without raising on error.

        Returns a response object for error case testing.
        """
        try:
            dto = CloseChannelDTO(channel_id=channel_id)
            await self.payment_service.settle_channel(dto)
            return UseCaseResponse(status_code=204, content=b"")
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )
