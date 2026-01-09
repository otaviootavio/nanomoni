"""Stress test: Open and close channel cycle - 1000 iterations."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_open_and_close_channel_1000_iterations(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Perform 1000 cycles of open channel, make payment, close channel.

    This test verifies the system can handle many channel lifecycle operations
    including opening, payment processing, and closing without failures.
    """
    # Setup: Register client and vendor once (reused across iterations)
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
    payment_amount = 100

    for iteration in range(1, num_iterations + 1):
        # 1. Open payment channel
        open_request = client.create_open_channel_request(
            vendor_public_key_der_b64, channel_amount
        )
        channel_response = await issuer_client.open_channel(open_request)
        computed_id = channel_response.computed_id

        assert channel_response.amount == channel_amount
        assert channel_response.balance == 0
        assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
        assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64

        # 2. Make one payment
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, payment_amount
        )
        payment_response = await vendor_client.receive_payment(
            computed_id, payment_envelope
        )

        assert payment_response.owed_amount == payment_amount
        assert payment_response.computed_id == computed_id

        # 3. Request channel closure
        await vendor_client.request_channel_closure(computed_id)

        # Verify channel is closed with correct balance
        channel_state = await issuer_client.get_channel(computed_id)
        assert channel_state.is_closed is True
        assert channel_state.balance == payment_amount
        assert channel_state.computed_id == computed_id
        assert channel_state.amount == channel_amount

        # Progress indicator every 100 iterations
        if iteration % 100 == 0:
            print(f"Completed {iteration}/{num_iterations} channel cycles")

    print(
        f"Successfully completed {num_iterations} channel open->payment->close cycles"
    )
