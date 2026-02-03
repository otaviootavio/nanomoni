"""Story: Vendor registers, issuer accepts it (use case-based test)."""

from __future__ import annotations

import pytest

from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_vendor_registers_issuer_accepts(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    """
    Story: Vendor registers, issuer accepts it.

    Phase1a: Vendor generates key pair and registers with issuer.
    The issuer creates an account with an initial balance.
    """
    # Given: A vendor with a public key
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64

    # When: Vendor registers with the issuer
    response = await issuer_client.register_account(vendor_public_key_der_b64)

    # Then: Account is created with initial balance
    assert response.client_public_key_der_b64 == vendor_public_key_der_b64
    assert response.balance > 0, "New account should have initial balance"

    # And: Re-registration is idempotent (returns existing account)
    second_response = await issuer_client.register_account(vendor_public_key_der_b64)
    assert second_response.client_public_key_der_b64 == vendor_public_key_der_b64
    assert second_response.balance == response.balance, (
        "Re-registration should not change balance"
    )
