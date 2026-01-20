"""Story: Client makes decreasing payment, vendor rejects it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_makes_decreasing_payment_vendor_rejects(
    require_services: None,  # pytest fixture - ensures services are available
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Client makes decreasing payment, vendor rejects it.

    Business rule: Payments must be monotonically increasing to prevent double-spending.
    """
    # Given: A channel with a payment (cumulative_owed_amount=200)
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # First payment: 200
    first_payment = client.create_payment_envelope(channel_id, 200)
    await vendor_client.receive_payment(channel_id, first_payment)

    # When: Client tries to send a payment with lower cumulative_owed_amount
    decreasing_payment = client.create_payment_envelope(channel_id, 150)

    # Then: Payment is rejected
    response = await vendor_client.receive_payment_raw(channel_id, decreasing_payment)
    assert response.status_code == 400, "Should reject decreasing payment"
    assert "increasing" in response.text.lower() or "greater" in response.text.lower()
