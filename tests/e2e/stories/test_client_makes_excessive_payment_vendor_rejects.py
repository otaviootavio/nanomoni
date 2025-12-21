"""Story: Client makes excessive payment, vendor rejects it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_makes_excessive_payment_vendor_rejects(
    docker_compose_stack: None,  # pytest fixture
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Client makes excessive payment, vendor rejects it.

    Business rule: owed_amount cannot exceed the channel's locked amount.
    """
    # Given: A channel with amount=1000
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # When: Client tries to send a payment exceeding channel amount
    excessive_payment = client.create_payment_envelope(
        computed_id,
        vendor_public_key_der_b64,
        1500,  # Exceeds channel amount of 1000
    )

    # Then: Payment is rejected
    response = await vendor_client.receive_payment_raw(computed_id, excessive_payment)
    assert response.status_code == 400, "Should reject payment exceeding channel amount"
    assert "exceed" in response.text.lower() or "amount" in response.text.lower()

