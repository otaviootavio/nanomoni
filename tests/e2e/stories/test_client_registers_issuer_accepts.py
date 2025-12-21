"""Story: Client registers, issuer accepts it."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_registers_issuer_accepts(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Client registers, issuer accepts it.

    Phase1a: Client generates key pair and registers with issuer.
    The issuer creates an account with an initial balance.
    """
    # Given: A client actor with a new key pair
    client = ClientActor()

    # When: Client registers with the issuer
    response = await issuer_client.register_account(client.public_key_der_b64)

    # Then: Account is created with initial balance
    assert response.client_public_key_der_b64 == client.public_key_der_b64
    assert response.balance > 0, "New account should have initial balance"

    # And: Re-registration is idempotent (returns existing account)
    second_response = await issuer_client.register_account(client.public_key_der_b64)
    assert second_response.client_public_key_der_b64 == client.public_key_der_b64
    assert second_response.balance == response.balance, (
        "Re-registration should not change balance"
    )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_multiple_clients_register_issuer_accepts_all(
    docker_compose_stack: None,  # pytest fixture
    issuer_client: IssuerTestClient,
) -> None:
    """
    Story: Multiple clients register, issuer accepts all.

    Each account is identified by its unique public key and gets its own balance.
    """
    # Given: Multiple client actors
    client1 = ClientActor()
    client2 = ClientActor()

    # When: Both clients register
    response1 = await issuer_client.register_account(client1.public_key_der_b64)
    response2 = await issuer_client.register_account(client2.public_key_der_b64)

    # Then: Both have separate accounts with balances
    assert response1.client_public_key_der_b64 != response2.client_public_key_der_b64
    assert response1.balance > 0
    assert response2.balance > 0
    # Accounts are independent (balances may be same initial value, but separate)
    assert response1.client_public_key_der_b64 == client1.public_key_der_b64
    assert response2.client_public_key_der_b64 == client2.public_key_der_b64

