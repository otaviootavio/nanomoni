"""Story: Issuer rejects tampered open-channel signature."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.tamper import tamper_b64_preserve_validity
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_issuer_rejects_tampered_open_channel_signature(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Issuer rejects open-channel request with tampered signature.

    Security rule: Invalid signatures must be rejected to prevent unauthorized channel creation.
    """
    # Given: A registered client and vendor
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: Client creates a valid open-channel request but tamper the signature
    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    tampered_request = open_request.model_copy(
        update={
            "open_signature_b64": tamper_b64_preserve_validity(
                open_request.open_signature_b64
            )
        }
    )

    # Then: Issuer rejects the request
    response = await issuer_client.open_channel_raw(tampered_request)
    assert response.status_code == 400, "Should reject tampered signature"
    response_data = response.json()
    assert "signature" in response_data.get("detail", "").lower()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_issuer_rejects_tampered_open_channel_payload(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Issuer rejects open-channel request with tampered payload.

    Security rule: Tampered payloads break signature verification and must be rejected.
    """
    # Given: A registered client and vendor
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: Client creates a valid open-channel request but tamper the payload
    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    tampered_request = open_request.model_copy(
        update={
            "open_payload_b64": tamper_b64_preserve_validity(
                open_request.open_payload_b64
            )
        }
    )

    # Then: Issuer rejects the request
    response = await issuer_client.open_channel_raw(tampered_request)
    assert response.status_code == 400, "Should reject tampered payload"
    response_data = response.json()
    assert "signature" in response_data.get("detail", "").lower()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_issuer_rejects_tampered_payword_open_channel_signature(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Issuer rejects PayWord open-channel request with tampered signature.

    Security rule: Invalid signatures must be rejected for PayWord channels too.
    """
    # Given: A registered client and vendor
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: Client creates a valid PayWord open-channel request but tamper the signature
    open_request, _payword = client.create_open_channel_request_payword(
        vendor_public_key_der_b64,
        amount=100,
        unit_value=1,
        max_k=100,
        pebble_count=8,
    )
    tampered_request = open_request.model_copy(
        update={
            "open_signature_b64": tamper_b64_preserve_validity(
                open_request.open_signature_b64
            )
        }
    )

    # Then: Issuer rejects the request
    response = await issuer_client.open_payword_channel_raw(tampered_request)
    assert response.status_code == 400, "Should reject tampered PayWord signature"
    response_data = response.json()
    assert "signature" in response_data.get("detail", "").lower()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_issuer_rejects_tampered_paytree_open_channel_signature(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Issuer rejects PayTree open-channel request with tampered signature.

    Security rule: Invalid signatures must be rejected for PayTree channels too.
    """
    # Given: A registered client and vendor
    client = ClientActor()
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    # When: Client creates a valid PayTree open-channel request but tamper the signature
    open_request, _paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=100,
        unit_value=1,
        max_i=100,
    )
    tampered_request = open_request.model_copy(
        update={
            "open_signature_b64": tamper_b64_preserve_validity(
                open_request.open_signature_b64
            )
        }
    )

    # Then: Issuer rejects the request
    response = await issuer_client.open_paytree_channel_raw(tampered_request)
    assert response.status_code == 400, "Should reject tampered PayTree signature"
    response_data = response.json()
    assert "signature" in response_data.get("detail", "").lower()
