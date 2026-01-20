"""Story: Vendor rejects tampered payment signature."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.tamper import tamper_envelope_signature
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_rejects_tampered_payment_signature(
    require_services: None,  # pytest fixture - ensures services are available
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Vendor rejects payment with tampered signature.

    Security rule: Invalid signatures must be rejected to prevent payment forgery.
    """
    # Given: An open payment channel
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # When: Client sends a payment with tampered signature
    valid_payment = client.create_payment_envelope(channel_id, 100)
    tampered_payment = tamper_envelope_signature(valid_payment)

    # Then: Vendor rejects the payment
    response = await vendor_client.receive_payment_raw(channel_id, tampered_payment)
    assert response.status_code == 400, "Should reject tampered payment signature"
    response_data = response.json()
    assert "invalid signature" in response_data.get("detail", "").lower()
