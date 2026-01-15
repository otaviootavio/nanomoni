"""Stress test: PayTree payment streaming - 5000 Merkle proof payments."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_paytree_payment_streaming_5000_payments(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Send 5000 PayTree payments sequentially through a single channel.

    This test verifies the system can handle a large number of sequential
    PayTree payments (Merkle proof verification) without failures.
    """
    # Setup: Register client and vendor
    client = ClientActor()
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Open PayTree-enabled payment channel
    num_payments = 5000
    unit_value = 1
    max_i = num_payments
    channel_amount = 1000000  # Large amount to support 5000 payments

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
    assert channel_response.paytree_root_b64 is not None

    # Send 5000 sequential PayTree payments (i = 1..5000)
    last_i = 0
    for i in range(1, num_payments + 1):
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)
        payment_response = await vendor_client.receive_paytree_payment(
            computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )

        assert payment_response.i == i
        assert payment_response.owed_amount == i * unit_value
        assert i > last_i
        last_i = i

        # Progress indicator every 500 payments
        if i % 500 == 0:
            print(f"Sent {i}/{num_payments} PayTree payments")

    # Close the channel to settle payments (PayTree settlement)
    await vendor_client.request_channel_closure_paytree(computed_id)

    # Verify final state after closure
    channel_state = await issuer_client.get_paytree_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.computed_id == computed_id
    assert channel_state.balance == last_i * unit_value
    assert channel_state.amount == channel_amount

    print(
        f"Successfully sent {num_payments} PayTree payments. Final i: {last_i}, "
        f"Final owed: {last_i * unit_value}"
    )
