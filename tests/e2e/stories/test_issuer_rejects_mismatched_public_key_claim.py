"""Story: Issuer rejects open-channel request with mismatched public key claim."""

from __future__ import annotations

import pytest

from nanomoni.application.issuer.dtos import OpenChannelRequestDTO
from nanomoni.application.shared.payment_channel_payloads import (
    OpenChannelRequestPayload,
)
from nanomoni.crypto.certificates import generate_envelope

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_issuer_rejects_mismatched_client_public_key_claim(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
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

    # When: ClientA creates a payload claiming clientB's public key, but signs with clientA's key
    # The DTO declares clientA's key (so signature verification passes), but payload claims clientB
    payload = OpenChannelRequestPayload(
        client_public_key_der_b64=clientB.public_key_der_b64,  # Claim clientB
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        amount=1000,
    )
    envelope = generate_envelope(
        clientA.private_key, payload.model_dump()
    )  # Sign with clientA

    mismatched_request = OpenChannelRequestDTO(
        client_public_key_der_b64=clientA.public_key_der_b64,  # Declare clientA (matches signature)
        open_payload_b64=envelope.payload_b64,
        open_signature_b64=envelope.signature_b64,
    )

    # Then: Issuer rejects due to mismatch between declared key and payload key
    response = await issuer_client.open_channel_raw(mismatched_request)
    assert response.status_code == 400, "Should reject mismatched public key claim"
    response_data = response.json()
    assert "mismatched" in response_data.get("detail", "").lower()
    assert "public key" in response_data.get("detail", "").lower()
