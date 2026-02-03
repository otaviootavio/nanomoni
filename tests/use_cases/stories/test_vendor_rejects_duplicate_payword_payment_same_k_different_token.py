"""Story: Vendor rejects duplicate PayWord payment (same k, different token) (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_vendor_rejects_duplicate_payword_payment_same_k_different_token(
    vendor_client: UseCaseVendorClient,
    issuer_client: UseCaseIssuerClient,
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

    # First payment at k=10
    k = 10
    token_k10 = payword.payment_proof_b64(k=k)
    await vendor_client.receive_payword_payment(channel_id, k=k, token_b64=token_k10)

    # Replay attempt: same k but token for a different k
    token_k11 = payword.payment_proof_b64(k=11)
    resp = await vendor_client.receive_payword_payment_raw(
        channel_id, k=k, token_b64=token_k11
    )
    assert resp.status_code == 400
    assert "duplicate" in (resp.json().get("detail", "").lower())
