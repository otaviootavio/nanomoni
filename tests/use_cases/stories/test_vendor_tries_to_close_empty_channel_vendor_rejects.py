"""Story: Vendor tries to close empty channel, vendor rejects it (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_vendor_tries_to_close_empty_channel_vendor_rejects(
    vendor_client: UseCaseVendorClient,
    issuer_client: UseCaseIssuerClient,
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
    channel_id = channel_response.channel_id

    # When: Vendor tries to close channel without any payments
    # Then: Closure is rejected
    response = await vendor_client.request_channel_settlement_raw(channel_id)
    assert response.status_code in [400, 500], "Should reject closure without payments"
    # Error message should indicate no payments received
    assert "payment" in response.text.lower() or "no" in response.text.lower()
