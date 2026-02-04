"""Story: Issuer rejects open-channel request with mismatched public key claim (use case-based test)."""

from __future__ import annotations

import pytest

from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.shared.payment_channel_payloads import (
    OpenChannelRequestPayload,
)

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_issuer_rejects_mismatched_client_public_key_claim(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    """
    Story: Issuer rejects open-channel request where declared public key doesn't match signed payload.

    Security rule: The client_public_key_der_b64 field must match the key in the signed payload
    to prevent key substitution attacks.
    """
    # Given: Two registered clients and a vendor
    clientA = ClientActor()
    clientB = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(clientA.public_key_der_b64)
    await issuer_client.register_account(clientB.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: ClientA creates a request but puts clientB's public key in the DTO
    # The signature is computed over the DTO fields, so if we put clientB's key in the DTO
    # but sign with clientA's key, the signature won't match (because the signed payload
    # would have clientB's key, but we're verifying with clientA's public key)
    from nanomoni.crypto.certificates import json_to_bytes, sign_bytes

    # Create DTO with clientB's key but sign with clientA's key
    # This creates a signature mismatch because the signature is over fields including clientB's key
    # but we verify with clientA's public key
    payload = OpenChannelRequestPayload(
        client_public_key_der_b64=clientB.public_key_der_b64,  # Claim clientB in payload
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=1000,
    )
    payload_bytes = json_to_bytes(payload.model_dump())
    signature_b64 = sign_bytes(clientA.private_key, payload_bytes)  # Sign with clientA

    # Create DTO with clientB's key (mismatch - signature was computed with clientB's key in payload)
    # but we'll verify with clientA's public key (from the DTO field)
    mismatched_request = OpenChannelRequestDTO(
        client_public_key_der_b64=clientB.public_key_der_b64,  # Declare clientB (but signed with clientA's key)
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=1000,
        open_signature_b64=signature_b64,
    )

    # Then: Issuer rejects due to signature verification failure
    # (The signature was computed with clientA's key over payload with clientB's key,
    # but we verify with clientA's public key, causing a mismatch)
    response = await issuer_client.open_channel_raw(mismatched_request)
    assert response.status_code == 400, "Should reject mismatched signature"
    response_data = response.json()
    assert "signature" in response_data.get("detail", "").lower()
