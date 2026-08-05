"""Story: Complete PayTree first-opt (pruned proof) flow - all actors succeed.

Runnable in Docker via pytest e2e so we can test the first-opt path against
real issuer/vendor/Redis. Uses a larger tree and consecutive payments so
settle relies on stored leaf hashes + rebuild (same as use-case test).
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_paytree_first_opt_flow_all_actors_succeed(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    """
    Story: Complete PayTree first-opt payment channel flow - all actors succeed.

    Same phases as test_complete_paytree_flow but with first-opt:
    pruned proofs per payment; vendor stores leaf hashes + siblings and rebuilds
    full proof at settle. Uses a larger tree and consecutive payments so we
    exercise the rebuild path (would fail without storing (0, i) -> leaf_b64).
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

    # Open PayTree first-opt channel (larger tree so pruned proof is short)
    channel_amount = 10_000
    unit_value = 1
    max_i = 128
    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_first_opt_channel(open_request)
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

    # PayTree first-opt payments: consecutive i so pruned proof is short
    prior_sent_indexes: list[int] = []
    indices = [10, 25, 50, 70]
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(
            i, prior_sent_indexes
        )
        prior_sent_indexes.append(i)
        resp = await vendor_client.receive_paytree_first_opt_payment(
            channel_id,
            i=i_val,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            paytree_max_i=max_i,
        )
        assert resp.channel_id == channel_id
        assert resp.i == i
        assert resp.cumulative_owed_amount == i * unit_value

    # Vendor settles and closes via PayTree (rebuild from first-opt store)
    await vendor_client.request_channel_settlement_paytree_first_opt(channel_id)

    # Assert balances after settlement
    final_cumulative_owed_amount = indices[-1] * unit_value
    client_after_settlement = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_settlement = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_settlement.balance == (
        client_initial_balance - final_cumulative_owed_amount
    )
    assert vendor_after_settlement.balance == (
        vendor_initial_balance + final_cumulative_owed_amount
    )

    channel_state = await issuer_client.get_paytree_first_opt_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == indices[-1] * unit_value
    assert channel_state.paytree_root_b64 is not None
