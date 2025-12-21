"""Story: Client opens payment channel, issuer accepts it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_opens_payment_channel_issuer_accepts(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client opens payment channel, issuer accepts it.

    Phase1b: Client opens a payment channel, locking funds from their account.
    """
    # Given: A registered client and vendor
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: Client opens a payment channel
    channel_amount = 1000
    open_request = client.create_open_channel_request(
        vendor_public_key_der_b64, channel_amount
    )
    channel_response = await issuer_client.open_channel(open_request)

    # Then: Channel is created with correct details
    assert channel_response.computed_id
    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0, "New channel starts with zero balance"
    assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
    assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64
    assert channel_response.salt_b64, "Channel should have a salt"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_queries_channel_state_issuer_returns(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client queries channel state, issuer returns it.

    The issuer is the authoritative source for channel metadata and state.
    """
    # Given: An open payment channel
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 500)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # When: Querying the channel state
    channel_state = await issuer_client.get_channel(computed_id)

    # Then: Channel details are returned correctly
    assert channel_state.computed_id == computed_id
    assert channel_state.amount == 500
    assert channel_state.is_closed is False
    assert channel_state.client_public_key_der_b64 == client.public_key_der_b64
    assert channel_state.vendor_public_key_der_b64 == vendor_public_key_der_b64

