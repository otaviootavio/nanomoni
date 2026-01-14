from __future__ import annotations

import asyncio
from typing import List, Optional

import httpx
from pydantic import BaseModel

from nanomoni.application.issuer.dtos import (
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
    RegistrationRequestDTO,
)
from nanomoni.application.shared.payment_channel_payloads import (
    OffChainTxPayload,
    OpenChannelRequestPayload,
)
from nanomoni.application.shared.payword_payloads import (
    PaywordOpenChannelRequestPayload,
)
from nanomoni.application.vendor.dtos import (
    CloseChannelDTO,
    ReceivePaymentDTO,
)
from nanomoni.application.vendor.payword_dtos import ReceivePaywordPaymentDTO
from nanomoni.crypto.certificates import generate_envelope, load_private_key_from_pem
from nanomoni.crypto.payword import Payword
from nanomoni.envs.client_env import get_settings
from nanomoni.infrastructure.issuer.issuer_client import AsyncIssuerClient
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync


async def run_client_flow() -> None:
    """
    Minimal client runner.

    This is intended to be executed inside Docker (or locally) to:
    - Register the client into the issuer
    - Open a payment channel to the vendor
    - Send a configurable sequence of off-chain payments to the vendor
    - Optionally request channel closure from the vendor
    """
    settings = get_settings()
    client_private_key = load_private_key_from_pem(settings.client_private_key_pem)

    payment_count = settings.client_payment_count
    # Default channel amount leaves a remainder so the client "receives funds back" on settlement.
    channel_amount = settings.client_channel_amount

    client_mode = settings.client_payment_mode
    if client_mode not in {"signature", "payword"}:
        raise RuntimeError("client_payment_mode must be 'signature' or 'payword'")

    # Generate monotonic sequence:
    # - signature mode: these are owed_amount values
    # - payword mode: these are k counters (owed_amount = k * unit_value)
    payments: List[int] = list(range(1, payment_count + 1))

    async with (
        AsyncIssuerClient(settings.issuer_base_url) as issuer,
        VendorClientAsync(settings.vendor_base_url) as vendor,
    ):
        # 1) Fetch vendor public key (required for opening channel + addressing payments)
        vendor_pk = await vendor.get_vendor_public_key()

        # 2) Ensure vendor is registered (idempotent in practice)
        try:
            await issuer.register(
                RegistrationRequestDTO(
                    client_public_key_der_b64=vendor_pk.public_key_der_b64
                )
            )
        except httpx.HTTPStatusError:
            # Vendor may already be registered; ignore 4xx/5xx here to keep runner minimal.
            pass

        # 3) Register client and capture starting balance (issuer returns existing balance).
        initial = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        initial_balance = initial.balance

        # 4) Open channel (client-signed envelope)
        payword_root_b64: Optional[str] = None
        payword_unit_value: Optional[int] = None
        payword_max_k: Optional[int] = None
        payword: Optional[Payword] = None

        if client_mode == "payword":
            # PayWord mode:
            # - Each payment sends a counter k; the money owed is owed_amount = k * unit_value.
            # - max_k is part of the channel commitment (persisted/enforced by vendor + issuer).
            #   We default max_k to payment_count for convenience, but they are different concepts:
            #   payment_count = how many payments this run; max_k = channel capacity in steps.
            # - The channel amount must cover the maximum possible owed amount:
            #   (max_k * unit_value) <= channel_amount  (issuer validates this at open).
            payword_unit_value = settings.client_payword_unit_value
            payword_max_k = settings.client_payword_max_k or payment_count
            if payword_max_k < payment_count:
                raise RuntimeError(
                    "CLIENT_PAYWORD_MAX_K must be >= CLIENT_PAYMENT_COUNT"
                )
            # Always use pebbling optimization in clients (trade memory for hashing).
            PAYWORD_PEBBLE_COUNT = 2**32
            payword = Payword.create(
                max_k=payword_max_k, pebble_count=PAYWORD_PEBBLE_COUNT
            )
            payword_root_b64 = payword.commitment_root_b64
            final_owed_amount = (payments[-1] * payword_unit_value) if payments else 0
        else:
            final_owed_amount = payments[-1] if payments else 0

        open_payload: BaseModel
        if client_mode == "payword":
            if (
                payword_root_b64 is None
                or payword_unit_value is None
                or payword_max_k is None
            ):
                raise RuntimeError("PayWord parameters not initialized")
            open_payload = PaywordOpenChannelRequestPayload(
                client_public_key_der_b64=settings.client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_pk.public_key_der_b64,
                amount=channel_amount,
                payword_root_b64=payword_root_b64,
                payword_unit_value=payword_unit_value,
                payword_max_k=payword_max_k,
                payword_hash_alg="sha256",
            )
        else:
            open_payload = OpenChannelRequestPayload(
                client_public_key_der_b64=settings.client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_pk.public_key_der_b64,
                amount=channel_amount,
            )
        open_env = generate_envelope(client_private_key, open_payload.model_dump())
        open_dto = OpenChannelRequestDTO(
            client_public_key_der_b64=settings.client_public_key_der_b64,
            open_payload_b64=open_env.payload_b64,
            open_signature_b64=open_env.signature_b64,
        )
        if client_mode == "payword":
            payword_channel = await issuer.open_payword_payment_channel(open_dto)
            computed_id = payword_channel.computed_id
        else:
            sig_channel = await issuer.open_payment_channel(open_dto)
            computed_id = sig_channel.computed_id

        # Read balance after lock (issuer register is idempotent; using it as a "get balance").
        after_open = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        balance_after_open = after_open.balance

        # 5) Payments
        if client_mode == "signature":
            # Precompute signed envelopes before sending requests, so the runtime path
            # measures mostly network + server-side verification (fairer vs payword pre-hashing).
            signed_payment_envs = []
            for owed_amount in payments:
                tx_payload = OffChainTxPayload(
                    computed_id=computed_id,
                    client_public_key_der_b64=settings.client_public_key_der_b64,
                    vendor_public_key_der_b64=vendor_pk.public_key_der_b64,
                    owed_amount=owed_amount,
                )
                signed_payment_envs.append(
                    generate_envelope(client_private_key, tx_payload.model_dump())
                )

            for pay_env in signed_payment_envs:
                await vendor.send_off_chain_payment(
                    computed_id,
                    ReceivePaymentDTO(envelope=pay_env),
                )
        else:
            if payword is None:
                raise RuntimeError("PayWord not initialized")
            for k in payments:
                token_b64 = payword.payment_proof_b64(k=k)
                await vendor.send_payword_payment(
                    computed_id,
                    ReceivePaywordPaymentDTO(k=k, token_b64=token_b64),
                )

        # 6) Closure request (vendor will call issuer settlement)
        if client_mode == "signature":
            await vendor.request_close_channel(CloseChannelDTO(computed_id=computed_id))
        else:
            await vendor.request_close_channel_payword(
                CloseChannelDTO(computed_id=computed_id)
            )

        # Wait until issuer marks the channel closed.
        for _ in range(120):  # ~60s
            get_dto = GetPaymentChannelRequestDTO(computed_id=computed_id)
            if client_mode == "payword":
                if (await issuer.get_payword_payment_channel(get_dto)).is_closed:
                    break
            else:
                if (await issuer.get_payment_channel(get_dto)).is_closed:
                    break
            await asyncio.sleep(0.5)
        else:
            raise AssertionError("Timed out waiting for channel closure on issuer")

        # 7) Assertion: client received remainder back on settlement.
        # Expected:
        # - After open: initial - channel_amount
        # - After close: initial - final_owed_amount
        final = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        final_balance = final.balance

        expected_after_open = initial_balance - channel_amount
        expected_final = initial_balance - final_owed_amount
        expected_remainder = channel_amount - final_owed_amount

        assert balance_after_open == expected_after_open, (
            f"Unexpected balance after open. got={balance_after_open}, "
            f"expected={expected_after_open}"
        )
        assert expected_remainder > 0, "Channel amount must exceed final owed amount"
        assert final_balance == expected_final, (
            f"Unexpected final client balance. got={final_balance}, expected={expected_final}"
        )
        assert final_balance - balance_after_open == expected_remainder, (
            "Client did not receive remainder back as expected. "
            f"got_delta={final_balance - balance_after_open}, expected_delta={expected_remainder}"
        )


def main() -> None:
    asyncio.run(run_client_flow())


if __name__ == "__main__":
    main()
