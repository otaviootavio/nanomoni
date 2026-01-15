"""Stress test: PayWord payment streaming - 5000 hash-chain payments."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient

# For large sequential streams, too few pebbles makes proof generation expensive.
# Keep this reasonably high so each payment stays fast without storing the full chain.
PAYWORD_PEBBLE_COUNT = 2047


@pytest.mark.asyncio
@pytest.mark.stress
async def test_stress_payword_payment_streaming_5000_payments(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Stress test: Send 5000 PayWord payments sequentially through a single channel.

    This test verifies the system can handle a large number of sequential
    PayWord payments (hash verification only) without failures.
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

    # Open PayWord-enabled payment channel
    num_payments = 5000
    unit_value = 1
    max_k = num_payments
    channel_amount = 1000000  # Large amount to support 5000 payments

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
    assert channel_response.payword_root_b64 is not None

    # Send 5000 sequential PayWord payments (k = 1..5000)
    last_k = 0
    for k in range(1, num_payments + 1):
        token_b64 = payword.payment_proof_b64(k=k)
        payment_response = await vendor_client.receive_payword_payment(
            computed_id, k=k, token_b64=token_b64
        )

        assert payment_response.k == k
        assert payment_response.owed_amount == k * unit_value
        assert k > last_k
        last_k = k

        # Progress indicator every 500 payments
        if k % 500 == 0:
            print(f"Sent {k}/{num_payments} PayWord payments")

    # Close the channel to settle payments (PayWord settlement)
    await vendor_client.request_channel_closure_payword(computed_id)

    # Verify final state after closure
    channel_state = await issuer_client.get_payword_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.computed_id == computed_id
    assert channel_state.balance == last_k * unit_value
    assert channel_state.amount == channel_amount

    print(
        f"Successfully sent {num_payments} PayWord payments. Final k: {last_k}, "
        f"Final owed: {last_k * unit_value}"
    )
