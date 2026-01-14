"""Stress test: Open and close PayWord channel cycle - 1000 iterations."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient

PAYWORD_PEBBLE_COUNT = 8


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_open_and_close_payword_channel_1000_iterations(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Perform 1000 cycles of open PayWord channel, make one PayWord payment, close.
    """
    client = ClientActor()
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    num_iterations = 1000
    channel_amount = 1000
    unit_value = 1
    max_k = 1000
    payment_k = 100

    for iteration in range(1, num_iterations + 1):
        # 1) Open PayWord-enabled channel
        open_request, payword = client.create_open_channel_request_payword(
            vendor_public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_k=max_k,
            pebble_count=PAYWORD_PEBBLE_COUNT,
        )
        channel_response = await issuer_client.open_payword_channel(open_request)
        computed_id = channel_response.computed_id

        assert channel_response.amount == channel_amount
        assert channel_response.balance == 0
        assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
        assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64
        assert channel_response.payword_root_b64 is not None

        # 2) Make one PayWord payment (k=payment_k)
        token_b64 = payword.payment_proof_b64(k=payment_k)
        payment_response = await vendor_client.receive_payword_payment(
            computed_id, k=payment_k, token_b64=token_b64
        )
        assert payment_response.k == payment_k
        assert payment_response.owed_amount == payment_k * unit_value

        # 3) Request channel closure (PayWord settlement)
        await vendor_client.request_channel_closure_payword(computed_id)

        channel_state = await issuer_client.get_payword_channel(computed_id)
        assert channel_state.is_closed is True
        assert channel_state.balance == payment_k * unit_value
        assert channel_state.computed_id == computed_id
        assert channel_state.amount == channel_amount

        if iteration % 100 == 0:
            print(f"Completed {iteration}/{num_iterations} PayWord channel cycles")

    print(
        f"Successfully completed {num_iterations} PayWord channel open->payment->close cycles"
    )
