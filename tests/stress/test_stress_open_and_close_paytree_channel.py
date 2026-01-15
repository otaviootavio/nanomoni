"""Stress test: Open and close PayTree channel cycle - 1000 iterations."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_open_and_close_paytree_channel_1000_iterations(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Perform 1000 cycles of open PayTree channel, make one PayTree payment, close.
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
    max_i = 1000
    payment_i = 100

    for iteration in range(1, num_iterations + 1):
        # 1) Open PayTree-enabled channel
        open_request, paytree = client.create_open_channel_request_paytree(
            vendor_public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_i=max_i,
        )
        channel_response = await issuer_client.open_paytree_channel(open_request)
        computed_id = channel_response.computed_id

        assert channel_response.amount == channel_amount
        assert channel_response.balance == 0
        assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
        assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64
        assert channel_response.paytree_root_b64 is not None

        # 2) Make one PayTree payment (i=payment_i)
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=payment_i)
        payment_response = await vendor_client.receive_paytree_payment(
            computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        assert payment_response.i == payment_i
        assert payment_response.owed_amount == payment_i * unit_value

        # 3) Request channel closure (PayTree settlement)
        await vendor_client.request_channel_closure_paytree(computed_id)

        channel_state = await issuer_client.get_paytree_channel(computed_id)
        assert channel_state.is_closed is True
        assert channel_state.balance == payment_i * unit_value
        assert channel_state.computed_id == computed_id
        assert channel_state.amount == channel_amount

        if iteration % 100 == 0:
            print(f"Completed {iteration}/{num_iterations} PayTree channel cycles")

    print(
        f"Successfully completed {num_iterations} PayTree channel open->payment->close cycles"
    )
