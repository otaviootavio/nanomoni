"""Story: Complete payment channel flow - all actors succeed (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_complete_payment_flow_all_actors_succeed(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
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
    client_initial_balance = registration_response.balance

    # Get vendor public key
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    # Register vendor (required for channel opening)
    vendor_registration = await issuer_client.register_account(
        vendor_public_key_der_b64
    )
    vendor_initial_balance = vendor_registration.balance

    # Phase1b: Open payment channel
    channel_amount = 1000
    open_request = client.create_open_channel_request(
        vendor_public_key_der_b64, channel_amount
    )
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0
    assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
    assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64

    # Assert funds are locked from the client's account when opening the channel.
    client_after_open = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_open = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_open.balance == client_initial_balance - channel_amount
    assert vendor_after_open.balance == vendor_initial_balance

    # Phase2a: First payment
    first_payment_owed = 50
    first_payment_envelope = client.create_payment_envelope(
        channel_id, first_payment_owed
    )
    first_payment_response = await vendor_client.receive_payment(
        channel_id, first_payment_envelope
    )
    assert first_payment_response.cumulative_owed_amount == first_payment_owed

    # Phase2b: Subsequent payments
    subsequent_payments = [100, 200, 350]
    last_cumulative_owed_amount = first_payment_owed

    for payment_owed in subsequent_payments:
        payment_envelope = client.create_payment_envelope(channel_id, payment_owed)
        payment_response = await vendor_client.receive_payment(
            channel_id, payment_envelope
        )
        assert payment_response.cumulative_owed_amount == payment_owed
        assert payment_owed > last_cumulative_owed_amount
        last_cumulative_owed_amount = payment_owed

    final_cumulative_owed_amount = last_cumulative_owed_amount

    # Phase3: Vendor initiates closure
    await vendor_client.request_channel_settlement(channel_id)

    # Assert balances after settlement:
    # - vendor is credited the cumulative owed amount
    # - client gets refund of remainder, so net client spend is the owed amount
    client_after_settlement = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_settlement = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_settlement.balance == (
        client_initial_balance - final_cumulative_owed_amount
    )
    assert vendor_after_settlement.balance == (
        vendor_initial_balance + final_cumulative_owed_amount
    )

    # Verify final state on issuer (authoritative source)
    channel_state = await issuer_client.get_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == final_cumulative_owed_amount
    assert channel_state.channel_id == channel_id
    assert channel_state.amount == channel_amount


@pytest.mark.asyncio
async def test_client_registers_and_opens_channel_issuer_accepts(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
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
    channel_state = await issuer_client.get_channel(channel_response.channel_id)
    assert channel_state.is_closed is False
