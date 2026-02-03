"""Story: Client makes excessive payment, vendor rejects it (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_client_makes_excessive_payment_vendor_rejects(
    vendor_client: UseCaseVendorClient,
    issuer_client: UseCaseIssuerClient,
) -> None:
    """
    Story: Client makes excessive payment, vendor rejects it.

    Business rule: cumulative_owed_amount cannot exceed the channel's locked amount.
    """
    # Given: A channel with amount=1000
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # When: Client tries to send a payment exceeding channel amount
    excessive_payment = client.create_payment_envelope(
        channel_id,
        1500,  # Exceeds channel amount of 1000
    )

    # Then: Payment is rejected
    response = await vendor_client.receive_payment_raw(channel_id, excessive_payment)
    assert response.status_code == 400, "Should reject payment exceeding channel amount"
    assert "exceed" in response.text.lower() or "amount" in response.text.lower()
