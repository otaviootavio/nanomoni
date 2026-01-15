"""Story: Vendor rejects payment with mismatched client public key."""

from __future__ import annotations

import pytest

from nanomoni.application.shared.payment_channel_payloads import OffChainTxPayload
from nanomoni.crypto.certificates import generate_envelope

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_rejects_mismatched_client_public_key_in_payment(
    require_services: None,  # pytest fixture - ensures services are available
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Vendor rejects payment where payload claims different client key than channel.

    Security rule: Payment payload's client_public_key_der_b64 must match the channel's
    client key to prevent payment substitution attacks.
    """
    # Given: An open channel for clientA
    clientA = ClientActor()
    clientB = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(clientA.public_key_der_b64)
    await issuer_client.register_account(clientB.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Open channel normally for clientA
    open_request = clientA.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # When: ClientA creates a payment payload claiming clientB's key, but signs with clientA's key
    payload = OffChainTxPayload(
        computed_id=computed_id,
        client_public_key_der_b64=clientB.public_key_der_b64,  # Claim clientB
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        owed_amount=100,
    )
    mismatched_payment = generate_envelope(clientA.private_key, payload.model_dump())

    # Then: Vendor rejects due to mismatch between payload key and channel key
    response = await vendor_client.receive_payment_raw(computed_id, mismatched_payment)
    assert response.status_code == 400, "Should reject mismatched client public key"
    response_data = response.json()
    assert "mismatched" in response_data.get("detail", "").lower()
    assert "client public key" in response_data.get("detail", "").lower()
