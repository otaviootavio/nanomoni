"""Story: Vendor accepts exact-duplicate PayTree payment (same i, same proof)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_accepts_duplicate_paytree_payment_same_i_same_proof(
    require_services: None,
    vendor_client: VendorTestClient,
    issuer_client: IssuerTestClient,
) -> None:
    client = ClientActor()

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=100,
        unit_value=1,
        max_i=100,
    )
    channel_response = await issuer_client.open_paytree_channel(open_request)
    computed_id = channel_response.computed_id

    i = 10
    i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)

    first = await vendor_client.receive_paytree_payment(
        computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
    )
    dup = await vendor_client.receive_paytree_payment(
        computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
    )

    assert first.computed_id == computed_id
    assert first.i == i
    assert first.owed_amount == i

    assert dup.computed_id == computed_id
    assert dup.i == i
    assert dup.owed_amount == i
