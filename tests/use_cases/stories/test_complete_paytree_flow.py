"""Story: Complete PayTree (Merkle tree) payment channel flow - all actors succeed (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_complete_paytree_flow_all_actors_succeed(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    """
    Story: Complete PayTree payment channel flow - all actors succeed.

    Phase1a: Client registers with issuer
    Phase1b: Client opens PayTree-enabled payment channel (commitment in open payload)
    Phase2: Client sends PayTree payments (i, leaf, siblings) to vendor
    Phase3: Vendor initiates PayTree settlement on issuer
    """
    client = ClientActor()

    # Register client + vendor
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.balance > 0
    client_initial_balance = registration_response.balance

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    vendor_registration = await issuer_client.register_account(
        vendor_public_key_der_b64
    )
    vendor_initial_balance = vendor_registration.balance

    # Open PayTree-enabled channel
    channel_amount = 100
    unit_value = 1
    max_i = 100
    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_channel(open_request)
    channel_id = channel_response.channel_id
    assert channel_response.amount == channel_amount
    assert channel_response.paytree_root_b64 is not None
    assert channel_response.paytree_unit_value == unit_value
    assert channel_response.paytree_max_i == max_i

    # Assert funds are locked from the client's account when opening the channel.
    client_after_open = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_open = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_open.balance == client_initial_balance - channel_amount
    assert vendor_after_open.balance == vendor_initial_balance

    # PayTree payments (monotonic i; may skip)
    indices = [10, 25, 70]
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)
        resp = await vendor_client.receive_paytree_payment(
            channel_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        assert resp.channel_id == channel_id
        assert resp.i == i
        assert resp.cumulative_owed_amount == i * unit_value

    # Vendor settles and closes via PayTree
    await vendor_client.request_channel_settlement_paytree(channel_id)

    # Assert balances after settlement:
    # - vendor is credited the cumulative owed amount
    # - client gets refund of remainder, so net client spend is the owed amount
    final_cumulative_owed_amount = indices[-1] * unit_value
    client_after_settlement = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_settlement = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_settlement.balance == (
        client_initial_balance - final_cumulative_owed_amount
    )
    assert vendor_after_settlement.balance == (
        vendor_initial_balance + final_cumulative_owed_amount
    )

    channel_state = await issuer_client.get_paytree_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == indices[-1] * unit_value
    assert channel_state.paytree_root_b64 is not None
