"""Story: Complete PayTree second-opt flow - all actors succeed.

Same wire proof, verification, and settle-time rebuild as first-opt; the
vendor additionally persists the computed ancestor hashes from verification,
not just the received nodes. Runnable in Docker via pytest e2e against real
issuer/vendor/Redis.
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_paytree_second_opt_flow_all_actors_succeed(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
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

    # Open PayTree second-opt channel (larger tree so pruned proof is short)
    channel_amount = 10_000
    unit_value = 1
    max_i = 128
    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_second_opt_channel(open_request)
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

    # PayTree second-opt payments: consecutive i so pruned proof is short
    prior_sent_indexes: list[int] = []
    indices = [10, 25, 50, 70]
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(
            i, prior_sent_indexes
        )
        prior_sent_indexes.append(i)
        resp = await vendor_client.receive_paytree_second_opt_payment(
            channel_id,
            i=i_val,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            paytree_max_i=max_i,
        )
        assert resp.channel_id == channel_id
        assert resp.i == i
        assert resp.cumulative_owed_amount == i * unit_value

    # Vendor settles and closes via PayTree (lazy rebuild from the node store)
    await vendor_client.request_channel_settlement_paytree_second_opt(channel_id)

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

    channel_state = await issuer_client.get_paytree_second_opt_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == indices[-1] * unit_value
    assert channel_state.paytree_root_b64 is not None
