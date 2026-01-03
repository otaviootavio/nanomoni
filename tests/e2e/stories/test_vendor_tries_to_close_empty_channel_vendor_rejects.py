"""Story: Vendor tries to close empty channel, vendor rejects it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_tries_to_close_empty_channel_vendor_rejects(
    docker_compose_stack: None,  # pytest fixture
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Vendor tries to close empty channel, vendor rejects it.

    Business rule: Closure requires at least one payment to determine settlement amount.
    """
    # Given: An open channel with no payments
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # When: Vendor tries to close channel without any payments
    # Then: Closure is rejected
    response = await vendor_client.request_channel_closure_raw(computed_id)
    assert response.status_code in [400, 500], "Should reject closure without payments"
    # Error message should indicate no payments received
    assert "payment" in response.text.lower() or "no" in response.text.lower()
