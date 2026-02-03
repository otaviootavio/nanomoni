"""Story: Vendor rejects PayWord token from different commitment root (use case-based test)."""

from __future__ import annotations

import pytest

from nanomoni.crypto.payword import Payword

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_vendor_rejects_payword_token_from_wrong_root(
    vendor_client: UseCaseVendorClient,
    issuer_client: UseCaseIssuerClient,
) -> None:
    """
    Story: Vendor rejects PayWord token generated from a different commitment root.

    Security rule: PayWord tokens must verify against the channel's committed root
    to prevent token substitution from other channels.
    """
    # Given: An open PayWord channel with root A
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Open channel with PaywordA
    open_request, paywordA = client.create_open_channel_request_payword(
        vendor_public_key_der_b64,
        amount=100,
        unit_value=1,
        max_k=100,
        pebble_count=8,
    )
    channel_response = await issuer_client.open_payword_channel(open_request)
    channel_id = channel_response.channel_id
    assert channel_response.payword_root_b64 == paywordA.commitment_root_b64

    # When: Client tries to send a token from PaywordB (different root)
    paywordB = Payword.create(
        max_k=100, pebble_count=8
    )  # Different seed => different root
    assert paywordB.commitment_root_b64 != paywordA.commitment_root_b64

    token_from_wrong_root = paywordB.payment_proof_b64(k=10)

    # Then: Vendor rejects the token from wrong root
    response = await vendor_client.receive_payword_payment_raw(
        channel_id, k=10, token_b64=token_from_wrong_root
    )
    assert response.status_code == 400, "Should reject token from wrong root"
    response_data = response.json()
    assert (
        "root" in response_data.get("detail", "").lower()
        or "mismatch" in response_data.get("detail", "").lower()
    )
