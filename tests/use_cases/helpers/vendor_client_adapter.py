"""Adapter that wraps vendor use cases for testing."""

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
    ReceivePaytreeStdPaymentDTO,
    ReceivePaytreeFirstOptPaymentDTO,
    PaytreePaymentResponseDTO,
)
from cryptography.exceptions import InvalidSignature

from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.application.vendor.use_cases.payword_payment import PaywordPaymentService
from nanomoni.application.vendor.use_cases.paytree_std_payment import (
    PaytreeStdPaymentService,
)
from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)


@dataclass(frozen=True)
class UseCaseResponse:
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
    def __init__(
        self,
        payment_service: PaymentService,
        payword_payment_service: PaywordPaymentService,
        paytree_std_payment_service: PaytreeStdPaymentService,
        paytree_first_opt_payment_service: PaytreeFirstOptPaymentService,
        vendor_public_key_der_b64: str,
    ) -> None:
        self.payment_service = payment_service
        self.payword_payment_service = payword_payment_service
        self.paytree_std_payment_service = paytree_std_payment_service
        self.paytree_first_opt_payment_service = paytree_first_opt_payment_service
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64

    async def get_public_key(self) -> VendorPublicKeyDTO:
        return VendorPublicKeyDTO(public_key_der_b64=self.vendor_public_key_der_b64)

    async def receive_payment(
        self, channel_id: str, payment_dto: ReceivePaymentDTO
    ) -> OffChainTxResponseDTO:
        return await self.payment_service.receive_payment(payment_dto)

    async def request_channel_settlement(self, channel_id: str) -> None:
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.payment_service.settle_channel(dto)

    # PayWord

    async def receive_payword_payment(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> PaywordPaymentResponseDTO:
        dto = ReceivePaywordPaymentDTO(k=k, token_b64=token_b64)
        return await self.payword_payment_service.receive_payword_payment(
            channel_id, dto
        )

    async def request_channel_settlement_payword(self, channel_id: str) -> None:
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.payword_payment_service.settle_channel(channel_id, dto)

    # PayTree Std

    async def receive_paytree_std_payment(
        self,
        channel_id: str,
        *,
        i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> PaytreePaymentResponseDTO:
        dto = ReceivePaytreeStdPaymentDTO(
            i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        return await self.paytree_std_payment_service.receive_payment(channel_id, dto)

    async def request_channel_settlement_paytree_std(self, channel_id: str) -> None:
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.paytree_std_payment_service.settle_channel(dto)

    async def receive_paytree_std_payment_raw(
        self,
        channel_id: str,
        *,
        i: int,
        leaf_b64: str,
        siblings_b64: list[str],
    ) -> UseCaseResponse:
        try:
            dto = ReceivePaytreeStdPaymentDTO(
                i=i, leaf_b64=leaf_b64, siblings_b64=siblings_b64
            )
            result = await self.paytree_std_payment_service.receive_payment(
                channel_id, dto
            )
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )

    # PayTree First-Opt

    async def receive_paytree_first_opt_payment(
        self,
        channel_id: str,
        *,
        i: int,
        leaf_b64: str,
        siblings_b64: list[str],
        paytree_max_i: int,
    ) -> PaytreePaymentResponseDTO:
        dto = ReceivePaytreeFirstOptPaymentDTO(
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            paytree_max_i=paytree_max_i,
        )
        return await self.paytree_first_opt_payment_service.receive_payment(
            channel_id, dto
        )

    async def request_channel_settlement_paytree_first_opt(
        self, channel_id: str
    ) -> None:
        dto = CloseChannelDTO(channel_id=channel_id)
        await self.paytree_first_opt_payment_service.settle_channel(dto)

    async def receive_paytree_first_opt_payment_raw(
        self,
        channel_id: str,
        *,
        i: int,
        leaf_b64: str,
        siblings_b64: list[str],
        paytree_max_i: int,
    ) -> UseCaseResponse:
        try:
            dto = ReceivePaytreeFirstOptPaymentDTO(
                i=i,
                leaf_b64=leaf_b64,
                siblings_b64=siblings_b64,
                paytree_max_i=paytree_max_i,
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

    # Generic raw helpers

    async def receive_payment_raw(
        self, channel_id: str, payment_dto: ReceivePaymentDTO
    ) -> UseCaseResponse:
        try:
            result = await self.payment_service.receive_payment(payment_dto)
            return UseCaseResponse(
                status_code=200, content=json.dumps(result.model_dump()).encode("utf-8")
            )
        except (ValueError, InvalidSignature) as e:
            error_msg = (
                str(e) if not isinstance(e, InvalidSignature) else "Invalid signature"
            )
            return UseCaseResponse(
                status_code=400,
                content=json.dumps({"detail": error_msg}).encode("utf-8"),
            )

    async def receive_payword_payment_raw(
        self, channel_id: str, *, k: int, token_b64: str
    ) -> UseCaseResponse:
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

    async def request_channel_settlement_raw(self, channel_id: str) -> UseCaseResponse:
        try:
            dto = CloseChannelDTO(channel_id=channel_id)
            await self.payment_service.settle_channel(dto)
            return UseCaseResponse(status_code=204, content=b"")
        except ValueError as e:
            return UseCaseResponse(
                status_code=400, content=json.dumps({"detail": str(e)}).encode("utf-8")
            )
