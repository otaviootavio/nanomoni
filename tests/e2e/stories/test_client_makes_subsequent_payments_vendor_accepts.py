"""Story: Client makes subsequent payments, vendor accepts them."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_makes_subsequent_payments_vendor_accepts(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client makes subsequent payments, vendor accepts them.

    Phase2b: Subsequent payments are validated against cached channel state.
    Each payment must have a higher cumulative_owed_amount than the previous one.
    """
    # Given: A channel with an initial payment
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 2000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # First payment
    first_payment = client.create_payment_envelope(channel_id, 100)
    await vendor_client.receive_payment(channel_id, first_payment)

    # When: Client sends subsequent payments with increasing amounts
    subsequent_amounts = [200, 350, 500, 750]
    last_owed = 100

    for cumulative_owed_amount in subsequent_amounts:
        payment_envelope = client.create_payment_envelope(
            channel_id, cumulative_owed_amount
        )
        payment_response = await vendor_client.receive_payment(
            channel_id, payment_envelope
        )

        # Then: Each payment is accepted and has correct amount
        assert payment_response.cumulative_owed_amount == cumulative_owed_amount
        assert cumulative_owed_amount > last_owed, (
            "Owed amount must be strictly increasing"
        )
        last_owed = cumulative_owed_amount


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_makes_sequence_of_payments_vendor_accepts_all(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client makes sequence of payments, vendor accepts all.

    This test focuses on the client's payment interaction pattern.
    """
    # Given: A client with an open channel
    client = ClientActor()
    await issuer_client.register_account(client.public_key_der_b64)

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 2000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # When: Client sends a sequence of payments
    payment_sequence = [10, 25, 50, 100, 200, 400]

    for cumulative_owed_amount in payment_sequence:
        payment_envelope = client.create_payment_envelope(
            channel_id, cumulative_owed_amount
        )
        payment_response = await vendor_client.receive_payment(
            channel_id, payment_envelope
        )
        assert payment_response.cumulative_owed_amount == cumulative_owed_amount

    # Then: Channel is still open (closure hasn't been initiated yet)
    channel_state = await issuer_client.get_channel(channel_id)
    # Note: Balance on issuer reflects final payment after closure
    # During active payments, balance tracks on vendor side
    assert channel_state.is_closed is False  # Still open
