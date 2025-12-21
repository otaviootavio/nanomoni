"""Story: Complete payment channel flow - all actors succeed."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_payment_flow_all_actors_succeed(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Complete payment channel flow - all actors succeed.

    This is the end-to-end integration test that orchestrates interactions
    across all bounded contexts:

    Phase1a: Client registers with issuer
    Phase1b: Client opens payment channel
    Phase2a: Client makes first payment to vendor
    Phase2b: Client makes subsequent payments
    Phase3: Vendor initiates closure (client has made payments)

    The test verifies the complete flow works end-to-end.
    """
    # Phase1a: Register client
    client = ClientActor()
    registration_request = client.create_registration_request()
    registration_response = await issuer_client.register_account(
        registration_request.client_public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    # Get vendor public key
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    # Register vendor (required for channel opening)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Phase1b: Open payment channel
    channel_amount = 1000
    open_request = client.create_open_channel_request(
        vendor_public_key_der_b64, channel_amount
    )
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0
    assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
    assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64

    # Phase2a: First payment
    first_payment_owed = 50
    first_payment_envelope = client.create_payment_envelope(
        computed_id, vendor_public_key_der_b64, first_payment_owed
    )
    first_payment_response = await vendor_client.receive_payment(
        computed_id, first_payment_envelope
    )
    assert first_payment_response.owed_amount == first_payment_owed

    # Phase2b: Subsequent payments
    subsequent_payments = [100, 200, 350]
    last_owed_amount = first_payment_owed

    for payment_owed in subsequent_payments:
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, payment_owed
        )
        payment_response = await vendor_client.receive_payment(
            computed_id, payment_envelope
        )
        assert payment_response.owed_amount == payment_owed
        assert payment_owed > last_owed_amount
        last_owed_amount = payment_owed

    final_owed_amount = last_owed_amount

    # Phase3: Vendor initiates closure
    await vendor_client.request_channel_closure(computed_id)

    # Verify final state on issuer (authoritative source)
    channel_state = await issuer_client.get_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == final_owed_amount
    assert channel_state.computed_id == computed_id
    assert channel_state.amount == channel_amount


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_registers_and_opens_channel_issuer_accepts(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client registers and opens channel, issuer accepts.

    This is a focused test for the client's initial setup flow.
    """
    # Given: A client actor
    client = ClientActor()

    # When: Client registers
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.balance > 0

    # And: Client opens a channel
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 500)
    channel_response = await issuer_client.open_channel(open_request)

    # Then: Channel is open and ready for payments
    assert channel_response.amount == 500
    assert channel_response.balance == 0
    # Verify channel state via issuer query
    channel_state = await issuer_client.get_channel(channel_response.computed_id)
    assert channel_state.is_closed is False

