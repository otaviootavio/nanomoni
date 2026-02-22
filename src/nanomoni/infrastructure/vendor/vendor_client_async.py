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
from ...application.vendor.paytree_first_opt_dtos import (
    PaytreeFirstOptPaymentResponseDTO,
    ReceivePaytreeFirstOptPaymentDTO,
)
from ...application.vendor.paytree_second_opt_dtos import (
    PaytreeSecondOptPaymentResponseDTO,
    ReceivePaytreeSecondOptPaymentDTO,
)
from ..http.http_client import HttpResponse
from ..http.http_client import AsyncHttpClient
from ..http.http_client import HttpRequestError
from ..http.http_client import HttpResponseError


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
                resp = await self._http.post(path, json=json)
                status = getattr(resp, "status", None) or resp.status_code
                transient_status = status == 429 or 500 <= status <= 599
                if transient_status and attempt < self._payment_retries:
                    await asyncio.sleep(self._payment_retry_backoff_s * (2**attempt))
                    continue
                # If the HTTP layer returned an error response instead of raising,
                # preserve HttpResponseError semantics for upstream callers.
                if status >= 400:
                    raise HttpResponseError(resp)
                # If we reach here, either we got a successful response or we've
                # exhausted retries without encountering an HTTP error.
                return resp
            except HttpResponseError as e:
                # AsyncHttpClient raises for non-2xx/3xx responses; recover the response
                # so we can treat some HTTP statuses as transient and retry.
                resp = e.response
                status = getattr(resp, "status", None) or resp.status_code
                transient_status = status == 429 or 500 <= status <= 599
                if transient_status and attempt < self._payment_retries:
                    await asyncio.sleep(self._payment_retry_backoff_s * (2**attempt))
                    continue
                # Non-transient HTTP error, or transient but we've exhausted retries:
                # re-raise so callers still see an exception.
                raise
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
        channel_id: str,
        dto: ReceivePaymentDTO,
    ) -> OffChainTxResponseDTO:
        """Send an off-chain payment to the vendor API.

        Uses ``ReceivePaymentDTO`` as the request body and validates the response
        as ``OffChainTxResponseDTO`` to keep this client aligned with the
        vendor API contract.
        """
        path = f"/vendor/channels/signature/{channel_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return OffChainTxResponseDTO.model_validate(resp.json())

    async def send_payword_payment(
        self,
        channel_id: str,
        dto: ReceivePaywordPaymentDTO,
    ) -> PaywordPaymentResponseDTO:
        """Send a PayWord payment to the vendor API."""
        path = f"/vendor/channels/payword/{channel_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaywordPaymentResponseDTO.model_validate(resp.json())

    async def request_settle_channel(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to settle a payment channel."""
        path = f"/vendor/channels/signature/{dto.channel_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def request_settle_channel_payword(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to settle a PayWord payment channel."""
        path = f"/vendor/channels/payword/{dto.channel_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def send_paytree_payment(
        self,
        channel_id: str,
        dto: ReceivePaytreePaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        """Send a PayTree payment to the vendor API."""
        path = f"/vendor/channels/paytree/{channel_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaytreePaymentResponseDTO.model_validate(resp.json())

    async def request_settle_channel_paytree(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to settle a PayTree payment channel."""
        path = f"/vendor/channels/paytree/{dto.channel_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def send_paytree_first_opt_payment(
        self,
        channel_id: str,
        dto: ReceivePaytreeFirstOptPaymentDTO,
    ) -> PaytreeFirstOptPaymentResponseDTO:
        """Send a PayTree First Opt payment to the vendor API."""
        path = f"/vendor/channels/paytree_first_opt/{channel_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaytreeFirstOptPaymentResponseDTO.model_validate(resp.json())

    async def request_settle_channel_paytree_first_opt(
        self, dto: CloseChannelDTO
    ) -> None:
        """Ask the vendor to settle a PayTree First Opt payment channel."""
        path = f"/vendor/channels/paytree_first_opt/{dto.channel_id}/closure-requests"
        await self._http.post(path, json=dto.model_dump())

    async def send_paytree_second_opt_payment(
        self,
        channel_id: str,
        dto: ReceivePaytreeSecondOptPaymentDTO,
    ) -> PaytreeSecondOptPaymentResponseDTO:
        """Send a PayTree Second Opt payment to the vendor API."""
        path = f"/vendor/channels/paytree_second_opt/{channel_id}/payments"
        resp = await self._post_with_payment_retries(path, json=dto.model_dump())
        return PaytreeSecondOptPaymentResponseDTO.model_validate(resp.json())

    async def request_settle_channel_paytree_second_opt(
        self, dto: CloseChannelDTO
    ) -> None:
        """Ask the vendor to settle a PayTree Second Opt payment channel."""
        path = f"/vendor/channels/paytree_second_opt/{dto.channel_id}/closure-requests"
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
