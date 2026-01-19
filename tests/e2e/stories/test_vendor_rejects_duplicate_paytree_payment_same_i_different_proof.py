"""Story: Vendor rejects duplicate PayTree payment (same i, different proof)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_vendor_rejects_duplicate_paytree_payment_same_i_different_proof(
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
    await vendor_client.receive_paytree_payment(
        computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
    )

    # Replay attempt: same i but proof for a different index
    _i2, leaf2_b64, siblings2_b64 = paytree.payment_proof(i=11)
    resp = await vendor_client.receive_paytree_payment_raw(
        computed_id, i=i_val, leaf_b64=leaf2_b64, siblings_b64=siblings2_b64
    )
    assert resp.status_code == 400
    assert "duplicate" in (resp.json().get("detail", "").lower())
