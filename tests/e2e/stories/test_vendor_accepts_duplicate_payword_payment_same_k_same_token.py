"""Story: Vendor accepts exact-duplicate PayWord payment (same k, same token)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_accepts_duplicate_payword_payment_same_k_same_token(
    require_services: None,
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
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

    k = 10
    token_b64 = payword.payment_proof_b64(k=k)

    first = await vendor_client.receive_payword_payment(
        channel_id, k=k, token_b64=token_b64
    )
    dup = await vendor_client.receive_payword_payment(
        channel_id, k=k, token_b64=token_b64
    )

    assert first.channel_id == channel_id
    assert first.k == k
    assert first.cumulative_owed_amount == k

    assert dup.channel_id == channel_id
    assert dup.k == k
    assert dup.cumulative_owed_amount == k
