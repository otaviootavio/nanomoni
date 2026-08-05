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

ClientMode = Literal[
    "signature",
    "payword",
    "paytree",
    "paytree_first_opt",
    "paytree_child_pair",
]

_VALID_MODES = {
    "signature",
    "payword",
    "paytree",
    "paytree_first_opt",
    "paytree_child_pair",
}


def validate_mode(mode: str) -> ClientMode:
    if mode not in _VALID_MODES:
        raise RuntimeError(
            "client_payment_mode must be one of: "
            "'signature', 'payword', 'paytree', 'paytree_first_opt', 'paytree_child_pair'"
        )
    return mode  # type: ignore[return-value]


async def open_channel_for_mode(
    issuer: AsyncIssuerClient,
    mode: ClientMode,
    open_dto: OpenChannelRequestDTO,
) -> str:
    if mode == "payword":
        payword_channel = await issuer.open_payword_payment_channel(open_dto)
        return payword_channel.channel_id
    elif mode == "paytree":
        paytree_channel = await issuer.open_paytree_std_payment_channel(open_dto)
        return paytree_channel.channel_id
    elif mode == "paytree_first_opt":
        paytree_channel = await issuer.open_paytree_first_opt_payment_channel(open_dto)
        return paytree_channel.channel_id
    elif mode == "paytree_child_pair":
        paytree_channel = await issuer.open_paytree_child_pair_payment_channel(open_dto)
        return paytree_channel.channel_id
    else:
        sig_channel = await issuer.open_payment_channel(open_dto)
        return sig_channel.channel_id


async def request_settle_for_mode(
    vendor: VendorClientAsync,
    mode: ClientMode,
    channel_id: str,
) -> None:
    close_dto = CloseChannelDTO(channel_id=channel_id)
    if mode == "payword":
        await vendor.request_settle_channel_payword(close_dto)
    elif mode == "paytree":
        await vendor.request_settle_channel_paytree_std(close_dto)
    elif mode == "paytree_first_opt":
        await vendor.request_settle_channel_paytree_first_opt(close_dto)
    elif mode == "paytree_child_pair":
        await vendor.request_settle_channel_paytree_child_pair(close_dto)
    else:
        await vendor.request_settle_channel(close_dto)


async def wait_until_closed(
    issuer: AsyncIssuerClient,
    mode: ClientMode,
    channel_id: str,
) -> None:
    for _ in range(120):  # ~60s
        get_dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
        if mode == "payword":
            if (await issuer.get_payword_payment_channel(get_dto)).is_closed:
                break
        elif mode == "paytree":
            if (await issuer.get_paytree_std_payment_channel(get_dto)).is_closed:
                break
        elif mode == "paytree_first_opt":
            if (await issuer.get_paytree_first_opt_payment_channel(get_dto)).is_closed:
                break
        elif mode == "paytree_child_pair":
            if (await issuer.get_paytree_child_pair_payment_channel(get_dto)).is_closed:
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
    if not payments:
        return 0

    if mode == "signature":
        return payments[-1]
    elif mode in {"payword", "paytree", "paytree_first_opt", "paytree_child_pair"}:
        if unit_value is None:
            raise ValueError(f"unit_value is required for {mode} mode")
        return payments[-1] * unit_value
    else:
        raise ValueError(f"Unknown mode: {mode}")
