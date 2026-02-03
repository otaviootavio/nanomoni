"""Story: Vendor rejects invalid PayWord token (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.tamper import tamper_b64_preserve_validity
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_vendor_rejects_invalid_payword_token(
    vendor_client: UseCaseVendorClient,
    issuer_client: UseCaseIssuerClient,
) -> None:
    """
    Story: Vendor rejects PayWord payment with invalid token.

    Security rule: PayWord tokens must verify against the committed root to prevent forgery.
    """
    # Given: An open PayWord channel
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

    # When: Client sends a payment with tampered token
    valid_token_b64 = payword.payment_proof_b64(k=10)
    tampered_token_b64 = tamper_b64_preserve_validity(valid_token_b64)

    # Then: Vendor rejects the invalid token
    response = await vendor_client.receive_payword_payment_raw(
        channel_id, k=10, token_b64=tampered_token_b64
    )
    assert response.status_code == 400, "Should reject invalid PayWord token"
    response_data = response.json()
    assert "invalid" in response_data.get("detail", "").lower()
    assert (
        "payword" in response_data.get("detail", "").lower()
        or "token" in response_data.get("detail", "").lower()
    )
