"""Story: Complete PayWord (hash-chain) payment channel flow - all actors succeed (use case-based test)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient

PAYWORD_PEBBLE_COUNT = 8


@pytest.mark.asyncio
async def test_complete_payword_flow_all_actors_succeed(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    """
    Story: Complete PayWord payment channel flow - all actors succeed.

    Phase1a: Client registers with issuer
    Phase1b: Client opens PayWord-enabled payment channel (commitment in open payload)
    Phase2: Client sends PayWord payments (k, token) to vendor
    Phase3: Vendor initiates PayWord settlement on issuer
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

    # Open PayWord-enabled channel
    channel_amount = 100
    unit_value = 1
    max_k = 100
    open_request, payword = client.create_open_channel_request_payword(
        vendor_public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_k=max_k,
        pebble_count=PAYWORD_PEBBLE_COUNT,
    )
    channel_response = await issuer_client.open_payword_channel(open_request)
    channel_id = channel_response.channel_id
    assert channel_response.amount == channel_amount
    assert channel_response.payword_root_b64 is not None
    assert channel_response.payword_unit_value == unit_value
    assert channel_response.payword_max_k == max_k

    # Assert funds are locked from the client's account when opening the channel.
    client_after_open = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_open = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_open.balance == client_initial_balance - channel_amount
    assert vendor_after_open.balance == vendor_initial_balance

    # PayWord payments (monotonic k; may skip)
    ks = [10, 25, 70]
    for k in ks:
        token_b64 = payword.payment_proof_b64(k=k)
        resp = await vendor_client.receive_payword_payment(
            channel_id, k=k, token_b64=token_b64
        )
        assert resp.channel_id == channel_id
        assert resp.k == k
        assert resp.cumulative_owed_amount == k * unit_value

    # Vendor settles and closes via PayWord
    await vendor_client.request_channel_settlement_payword(channel_id)

    # Assert balances after settlement:
    # - vendor is credited the cumulative owed amount
    # - client gets refund of remainder, so net client spend is the owed amount
    final_cumulative_owed_amount = ks[-1] * unit_value
    client_after_settlement = await issuer_client.get_account(client.public_key_der_b64)
    vendor_after_settlement = await issuer_client.get_account(vendor_public_key_der_b64)
    assert client_after_settlement.balance == (
        client_initial_balance - final_cumulative_owed_amount
    )
    assert vendor_after_settlement.balance == (
        vendor_initial_balance + final_cumulative_owed_amount
    )

    channel_state = await issuer_client.get_payword_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == ks[-1] * unit_value
    assert channel_state.payword_root_b64 is not None
