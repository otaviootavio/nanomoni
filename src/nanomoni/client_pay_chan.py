from __future__ import annotations

import asyncio
import os

import httpx

from nanomoni.application.issuer.dtos import (
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
    RegistrationRequestDTO,
)
from nanomoni.application.shared.payment_channel_payloads import (
    OffChainTxPayload,
    OpenChannelRequestPayload,
)
from nanomoni.application.vendor.dtos import CloseChannelDTO, ReceivePaymentDTO
from nanomoni.crypto.certificates import generate_envelope, load_private_key_from_pem
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

    try:
        payment_count = int(os.environ["CLIENT_PAYMENT_COUNT"])
        # Default channel amount leaves a remainder so the client "receives funds back" on settlement.
        channel_amount = int(os.environ["CLIENT_CHANNEL_AMOUNT"])
    except KeyError as e:
        raise RuntimeError(f"Missing required environment variable: {e.args[0]}") from e

    # Generate monotonic owed_amounts (required by vendor validation).
    payments: list[int] = list(range(1, payment_count + 1))
    final_owed_amount = payments[-1] if payments else 0

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
        open_payload = OpenChannelRequestPayload(
            client_public_key_der_b64=settings.client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_pk.public_key_der_b64,
            amount=channel_amount,
        )
        open_env = generate_envelope(client_private_key, open_payload.model_dump())
        channel = await issuer.open_payment_channel(
            OpenChannelRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64,
                open_payload_b64=open_env.payload_b64,
                open_signature_b64=open_env.signature_b64,
            )
        )

        # Read balance after lock (issuer register is idempotent; using it as a "get balance").
        after_open = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        balance_after_open = after_open.balance

        # 5) Payments
        for owed_amount in payments:
            tx_payload = OffChainTxPayload(
                computed_id=channel.computed_id,
                client_public_key_der_b64=settings.client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_pk.public_key_der_b64,
                owed_amount=owed_amount,
            )
            pay_env = generate_envelope(client_private_key, tx_payload.model_dump())
            await vendor.send_off_chain_payment(
                channel.computed_id,
                ReceivePaymentDTO(envelope=pay_env),
            )

        # 6) Closure request (vendor will call issuer settlement)
        await vendor.request_close_channel(
            CloseChannelDTO(computed_id=channel.computed_id)
        )

        # Wait until issuer marks the channel closed.
        for _ in range(120):  # ~60s
            ch = await issuer.get_payment_channel(
                GetPaymentChannelRequestDTO(computed_id=channel.computed_id)
            )
            if ch.is_closed:
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
