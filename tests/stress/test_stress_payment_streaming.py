"""Stress test: Payment streaming - 5000 offchain payments."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_payment_streaming_5000_payments(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Send 5000 offchain payments sequentially through a single channel.

    This test verifies the system can handle a large number of sequential
    offchain payments without failures or performance degradation.
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

    # Open payment channel
    channel_amount = 1000000  # Large amount to support 5000 payments
    open_request = client.create_open_channel_request(
        vendor_public_key_der_b64, channel_amount
    )
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0

    # Send 5000 sequential offchain payments
    num_payments = 5000
    last_owed_amount = 0

    for payment_number in range(1, num_payments + 1):
        owed_amount = payment_number  # Cumulative owed amount (1, 2, 3, ..., 5000)
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, owed_amount
        )
        payment_response = await vendor_client.receive_payment(
            computed_id, payment_envelope
        )

        assert payment_response.owed_amount == owed_amount
        assert payment_response.computed_id == computed_id
        assert owed_amount > last_owed_amount

        last_owed_amount = owed_amount

        # Progress indicator every 500 payments
        if payment_number % 500 == 0:
            print(f"Sent {payment_number}/{num_payments} payments")

    # Close the channel to settle payments
    await vendor_client.request_channel_closure(computed_id)

    # Verify final state after closure
    channel_state = await issuer_client.get_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.computed_id == computed_id
    assert channel_state.balance == last_owed_amount
    assert channel_state.amount == channel_amount

    print(
        f"Successfully sent {num_payments} payments. Final owed amount: {last_owed_amount}"
    )
