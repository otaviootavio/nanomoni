"""Shared helpers for client payment channel operations."""

from __future__ import annotations

import asyncio
from typing import Literal

from nanomoni.application.issuer.dtos import (
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
)
from nanomoni.application.vendor.dtos import CloseChannelDTO
from nanomoni.infrastructure.issuer.issuer_client import AsyncIssuerClient
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync

ClientMode = Literal["signature", "payword", "paytree"]


def validate_mode(mode: str) -> ClientMode:
    """Validate that the mode is one of the supported payment modes."""
    if mode not in {"signature", "payword", "paytree"}:
        raise RuntimeError(
            "client_payment_mode must be 'signature', 'payword', or 'paytree'"
        )
    return mode  # type: ignore[return-value]


async def open_channel_for_mode(
    issuer: AsyncIssuerClient,
    mode: ClientMode,
    open_dto: OpenChannelRequestDTO,
) -> str:
    """Open a payment channel using the appropriate API endpoint for the mode.

    Returns:
        The channel_id of the opened channel.
    """
    if mode == "payword":
        payword_channel = await issuer.open_payword_payment_channel(open_dto)
        return payword_channel.channel_id
    elif mode == "paytree":
        paytree_channel = await issuer.open_paytree_payment_channel(open_dto)
        return paytree_channel.channel_id
    else:
        sig_channel = await issuer.open_payment_channel(open_dto)
        return sig_channel.channel_id


async def request_settle_for_mode(
    vendor: VendorClientAsync,
    mode: ClientMode,
    channel_id: str,
) -> None:
    """Request channel settlement using the appropriate API endpoint for the mode."""
    close_dto = CloseChannelDTO(channel_id=channel_id)
    if mode == "payword":
        await vendor.request_settle_channel_payword(close_dto)
    elif mode == "paytree":
        await vendor.request_settle_channel_paytree(close_dto)
    else:
        await vendor.request_settle_channel(close_dto)


async def wait_until_closed(
    issuer: AsyncIssuerClient,
    mode: ClientMode,
    channel_id: str,
) -> None:
    """Wait until the issuer marks the channel as closed.

    Raises:
        AssertionError: If the channel is not closed within the timeout period.
    """
    for _ in range(120):  # ~60s
        get_dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        if mode == "payword":
            if (await issuer.get_payword_payment_channel(get_dto)).is_closed:
                break
        elif mode == "paytree":
            if (await issuer.get_paytree_payment_channel(get_dto)).is_closed:
                break
        else:
            if (await issuer.get_payment_channel(get_dto)).is_closed:
                break
        await asyncio.sleep(0.5)
    else:
        raise AssertionError("Timed out waiting for channel closure on issuer")


def compute_final_cumulative_owed_amount(
    mode: ClientMode,
    payments: list[int],
    unit_value: int | None = None,
) -> int:
    """Compute the final owed amount based on the mode and payment sequence.

    Args:
        mode: The payment mode ("signature", "payword", or "paytree")
        payments: List of payment values (cumulative_owed_amount for signature, k/i for payword/paytree)
        unit_value: Unit value for payword/paytree modes (required for those modes)

    Returns:
        The final owed amount.
    """
    if not payments:
        return 0

    if mode == "signature":
        return payments[-1]
    elif mode in {"payword", "paytree"}:
        if unit_value is None:
            raise ValueError(f"unit_value is required for {mode} mode")
        return payments[-1] * unit_value
    else:
        raise ValueError(f"Unknown mode: {mode}")
