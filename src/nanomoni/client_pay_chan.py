from __future__ import annotations

import asyncio

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
)
from nanomoni.client import (
    common,
    paytree,
    paytree_first_opt,
    paytree_second_opt,
    payword,
    signature,
)
from nanomoni.crypto.certificates import load_private_key_from_pem
from nanomoni.crypto.paytree import Paytree
from nanomoni.crypto.paytree_first_opt import PaytreeFirstOpt
from nanomoni.crypto.paytree_second_opt import PaytreeSecondOpt
from nanomoni.crypto.payword import Payword
from nanomoni.envs.client_env import get_settings
from nanomoni.infrastructure.http.http_client import HttpError
from nanomoni.infrastructure.issuer.issuer_client import AsyncIssuerClient
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync


PAYWORD_NOT_INITIALIZED = "PayWord object should be initialized"
PAYTREE_NOT_INITIALIZED = "PayTree object should be initialized"


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

    client_mode = common.validate_mode(settings.client_payment_mode)

    # Generate monotonic sequence:
    # - signature mode: these are cumulative_owed_amount values
    # - payword mode: these are k counters (cumulative_owed_amount = k * unit_value)
    payments: list[int] = list(range(1, payment_count + 1))

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
        except HttpError:
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
        # Initialize mode-specific commitments and compute final owed amount
        final_cumulative_owed_amount: int
        payword_obj: Payword | None = None
        paytree_obj: Paytree | None = None
        paytree_first_opt_obj: PaytreeFirstOpt | None = None
        paytree_second_opt_obj: PaytreeSecondOpt | None = None

        if client_mode == "payword":
            payword_obj, payword_root_b64, payword_unit_value, payword_max_k = (
                payword.init_commitment(settings, payment_count)
            )
            final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
                client_mode, payments, payword_unit_value
            )
        elif client_mode == "paytree":
            paytree_obj, paytree_root_b64, paytree_unit_value, paytree_max_i = (
                paytree.init_commitment(settings, payment_count)
            )
            final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
                client_mode, payments, paytree_unit_value
            )
        elif client_mode == "paytree_first_opt":
            (
                paytree_first_opt_obj,
                paytree_first_opt_root_b64,
                paytree_first_opt_unit_value,
                paytree_first_opt_max_i,
            ) = paytree_first_opt.init_commitment(settings, payment_count)
            final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
                client_mode, payments, paytree_first_opt_unit_value
            )
        elif client_mode == "paytree_second_opt":
            (
                paytree_second_opt_obj,
                paytree_second_opt_root_b64,
                paytree_second_opt_unit_value,
                paytree_second_opt_max_i,
            ) = paytree_second_opt.init_commitment(settings, payment_count)
            final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
                client_mode, payments, paytree_second_opt_unit_value
            )
        else:
            final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
                client_mode, payments
            )

        # Sign and send open channel request
        if client_mode == "payword":
            open_dto = payword.build_open_channel_request(
                client_private_key,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                channel_amount,
                payword_root_b64,
                payword_unit_value,
                payword_max_k,
            )
        elif client_mode == "paytree":
            open_dto = paytree.build_open_channel_request(
                client_private_key,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                channel_amount,
                paytree_root_b64,
                paytree_unit_value,
                paytree_max_i,
            )
        elif client_mode == "paytree_first_opt":
            open_dto = paytree_first_opt.build_open_channel_request(
                client_private_key,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                channel_amount,
                paytree_first_opt_root_b64,
                paytree_first_opt_unit_value,
                paytree_first_opt_max_i,
            )
        elif client_mode == "paytree_second_opt":
            open_dto = paytree_second_opt.build_open_channel_request(
                client_private_key,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                channel_amount,
                paytree_second_opt_root_b64,
                paytree_second_opt_unit_value,
                paytree_second_opt_max_i,
            )
        else:
            open_dto = signature.build_open_channel_request(
                client_private_key,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                channel_amount,
            )
        channel_id = await common.open_channel_for_mode(issuer, client_mode, open_dto)

        # Read balance after lock (issuer register is idempotent; using it as a "get balance").
        after_open = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        balance_after_open = after_open.balance

        # 5) Payments
        if client_mode == "signature":
            payment_dtos = signature.prepare_payments(
                channel_id,
                settings.client_public_key_der_b64,
                vendor_pk.public_key_der_b64,
                client_private_key,
                payments,
            )
            await signature.send_payments(vendor, channel_id, payment_dtos)
        elif client_mode == "payword":
            if payword_obj is None:
                raise RuntimeError(PAYWORD_NOT_INITIALIZED)
            # Type narrowing: mypy now knows payword_obj is not None after the check
            payword_for_payments: Payword = payword_obj
            await payword.send_payments(
                vendor, channel_id, payword_for_payments, payments
            )
        elif client_mode == "paytree":
            if paytree_obj is None:
                raise RuntimeError(PAYTREE_NOT_INITIALIZED)
            # Type narrowing: mypy now knows paytree_obj is not None after the check
            paytree_for_payments: Paytree = paytree_obj
            await paytree.send_payments(
                vendor, channel_id, paytree_for_payments, payments
            )
        elif client_mode == "paytree_first_opt":
            if paytree_first_opt_obj is None:
                raise RuntimeError(PAYTREE_NOT_INITIALIZED)
            paytree_first_opt_for_payments: PaytreeFirstOpt = paytree_first_opt_obj
            await paytree_first_opt.send_payments(
                vendor, channel_id, paytree_first_opt_for_payments, payments
            )
        elif client_mode == "paytree_second_opt":
            if paytree_second_opt_obj is None:
                raise RuntimeError(PAYTREE_NOT_INITIALIZED)
            paytree_second_opt_for_payments: PaytreeSecondOpt = paytree_second_opt_obj
            await paytree_second_opt.send_payments(
                vendor, channel_id, paytree_second_opt_for_payments, payments
            )
        else:
            raise RuntimeError(f"Unsupported client mode: {client_mode}")

        # 6) Closure request (vendor will call issuer settlement)
        await common.request_settle_for_mode(vendor, client_mode, channel_id)

        # Wait until issuer marks the channel closed.
        await common.wait_until_closed(issuer, client_mode, channel_id)

        # 7) Assertion: client received remainder back on settlement.
        # Expected:
        # - After open: initial - channel_amount
        # - After close: initial - final_cumulative_owed_amount
        final = await issuer.register(
            RegistrationRequestDTO(
                client_public_key_der_b64=settings.client_public_key_der_b64
            )
        )
        final_balance = final.balance

        expected_after_open = initial_balance - channel_amount
        expected_final = initial_balance - final_cumulative_owed_amount
        expected_remainder = channel_amount - final_cumulative_owed_amount

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
