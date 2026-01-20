"""Story: Vendor rejects non-monotonic PayWord k value."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_rejects_nonmonotonic_payword_k(
    require_services: None,  # pytest fixture - ensures services are available
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Vendor rejects PayWord payment with decreasing k value.

    Security rule: PayWord k must be monotonically increasing to prevent replay attacks.
    """
    # Given: An open PayWord channel with one payment at k=10
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request, payword = client.create_open_channel_request_payword(
        vendor_public_key_der_b64,
        amount=100,
        unit_value=1,
        max_k=100,
        pebble_count=8,
    )
    channel_response = await issuer_client.open_payword_channel(open_request)
    channel_id = channel_response.channel_id

    # First payment at k=10
    token_k10 = payword.payment_proof_b64(k=10)
    await vendor_client.receive_payword_payment(channel_id, k=10, token_b64=token_k10)

    # When: Client tries to send a payment with k=5 (decreasing)
    token_k5 = payword.payment_proof_b64(k=5)

    # Then: Vendor rejects the non-monotonic k
    response = await vendor_client.receive_payword_payment_raw(
        channel_id, k=5, token_b64=token_k5
    )
    assert response.status_code == 400, "Should reject non-monotonic k"
    response_data = response.json()
    assert (
        "increasing" in response_data.get("detail", "").lower()
        or "greater" in response_data.get("detail", "").lower()
    )
