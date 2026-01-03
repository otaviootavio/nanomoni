"""Story: Vendor closes payment channel, issuer accepts it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_closes_channel_issuer_accepts(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Vendor closes payment channel, issuer accepts it.

    Phase3: Vendor initiates closure after client has made payments.
    """
    # Given: A channel with payments
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 2000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # Client makes payments
    payments = [50, 150, 300, 500]
    for owed_amount in payments:
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, owed_amount
        )
        await vendor_client.receive_payment(computed_id, payment_envelope)

    # When: Vendor initiates closure
    await vendor_client.request_channel_closure(computed_id)

    # Then: Channel is closed with correct final balance
    channel_state = await issuer_client.get_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == 500  # Final payment amount


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_tries_to_close_already_closed_channel_vendor_handles_gracefully(
    docker_compose_stack: None,  # pytest fixture
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Vendor tries to close already-closed channel, vendor handles gracefully.

    Business rule: Closure is idempotent or should be rejected if already closed.
    """
    # Given: A closed channel
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # Receive payment and close
    payment = client.create_payment_envelope(
        computed_id, vendor_public_key_der_b64, 300
    )
    await vendor_client.receive_payment(computed_id, payment)
    await vendor_client.request_channel_closure(computed_id)

    # When: Vendor tries to close again
    # Then: Second closure should be handled gracefully (idempotent or rejected)
    # The implementation returns None if already closed, which is acceptable
    await vendor_client.request_channel_closure(computed_id)  # Should not raise
