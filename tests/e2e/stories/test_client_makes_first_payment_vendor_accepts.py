"""Story: Client makes first payment, vendor accepts it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_makes_first_payment_vendor_accepts(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Client makes first payment, vendor accepts it.

    Phase2a: First payment triggers vendor to verify channel with issuer
    and cache the channel locally before accepting the payment.
    """
    # Given: A client and vendor are registered, and a payment channel is open
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    # When: Client sends first payment
    first_payment_owed = 50
    payment_envelope = client.create_payment_envelope(
        computed_id, vendor_public_key_der_b64, first_payment_owed
    )
    payment_response = await vendor_client.receive_payment(
        computed_id, payment_envelope
    )

    # Then: Payment is accepted
    assert payment_response.owed_amount == first_payment_owed
    assert payment_response.computed_id == computed_id
    assert payment_response.client_public_key_der_b64 == client.public_key_der_b64
    assert payment_response.vendor_public_key_der_b64 == vendor_public_key_der_b64
