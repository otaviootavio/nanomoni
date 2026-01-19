from __future__ import annotations

import asyncio
from typing import Any, Optional, Type
from types import TracebackType

import aiohttp

from ...application.vendor.dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
    VendorPublicKeyDTO,
)
from ...application.vendor.payword_dtos import (
    PaywordPaymentResponseDTO,
    ReceivePaywordPaymentDTO,
)
from ...application.vendor.paytree_dtos import (
    PaytreePaymentResponseDTO,
    ReceivePaytreePaymentDTO,
)
from ..http.http_client import HttpResponse
from ..http.http_client import AsyncHttpClient
from ..http.http_client import HttpRequestError


class VendorClientAsync:
    """Asynchronous client for talking to the Vendor HTTP API."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        *,
        payment_retries: int = 2,
        payment_retry_backoff_s: float = 0.15,
    ) -> None:
        self._http = AsyncHttpClient(base_url, timeout=timeout)
        self._payment_retries = payment_retries
        self._payment_retry_backoff_s = payment_retry_backoff_s

    async def get_vendor_public_key(self) -> VendorPublicKeyDTO:
        """Fetch the vendor's public key (DER b64) from the vendor API.

        The JSON response is validated into ``VendorPublicKeyDTO`` to ensure
        runtime contract compliance.
        """
        resp = await self._http.get("/vendor/keys/public")
        return VendorPublicKeyDTO.model_validate(resp.json())

    async def _post_with_payment_retries(
        self,
        path: str,
        *,
        json: dict[str, Any],
    ) -> HttpResponse:
        """
        POST helper with transient retry/backoff.

        This is intended for payment-like endpoints where an exact-duplicate retry is safe
        (vendor side enforces idempotency for exact duplicates).
        """
        for attempt in range(self._payment_retries + 1):
            try:
                return await self._http.post(path, json=json)
            except HttpRequestError as e:
                # HttpRequestError exposes the underlying exception on .cause,
                # but also fall back to __cause__ for safety.
                cause = getattr(e, "cause", None) or getattr(e, "__cause__", None)
                transient = isinstance(
                    cause,
                    (
                        asyncio.TimeoutError,
                        aiohttp.ServerDisconnectedError,
                        aiohttp.ClientConnectionError,
                        aiohttp.ClientOSError,
                    ),
                )
                if transient and attempt < self._payment_retries:
                    await asyncio.sleep(self._payment_retry_backoff_s * (2**attempt))
                    continue
                raise

        # loop always returns or raises, but keep mypy satisfied.
        raise RuntimeError(
            "Unreachable: exhausted retries without returning or raising"
        )

    async def send_off_chain_payment(
        self,
        computed_id: str,
        dto: ReceivePaymentDTO,
    ) -> OffChainTxResponseDTO:
        """Send an off-chain payment to the vendor API.

        Uses ``ReceivePaymentDTO`` as the request body and validates the response
        as ``OffChainTxResponseDTO`` to keep this client aligned with the
        vendor API contract.
        """
        path = f"/vendor/channels/signature/{computed_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return OffChainTxResponseDTO.model_validate(resp.json())

    async def send_payword_payment(
        self,
        computed_id: str,
        dto: ReceivePaywordPaymentDTO,
    ) -> PaywordPaymentResponseDTO:
        """Send a PayWord payment to the vendor API."""
        path = f"/vendor/channels/payword/{computed_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaywordPaymentResponseDTO.model_validate(resp.json())

    async def request_close_channel(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to close a payment channel."""
        path = f"/vendor/channels/signature/{dto.computed_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def request_close_channel_payword(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to close a PayWord payment channel."""
        path = f"/vendor/channels/payword/{dto.computed_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def send_paytree_payment(
        self,
        computed_id: str,
        dto: ReceivePaytreePaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        """Send a PayTree payment to the vendor API."""
        path = f"/vendor/channels/paytree/{computed_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaytreePaymentResponseDTO.model_validate(resp.json())

    async def request_close_channel_paytree(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to close a PayTree payment channel."""
        path = f"/vendor/channels/paytree/{dto.computed_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "VendorClientAsync":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.aclose()
