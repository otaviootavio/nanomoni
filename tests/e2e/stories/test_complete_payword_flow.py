"""Story: Complete PayWord (hash-chain) payment channel flow - all actors succeed."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient

PAYWORD_PEBBLE_COUNT = 8


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_payword_flow_all_actors_succeed(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
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

    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

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

    channel_state = await issuer_client.get_payword_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == ks[-1] * unit_value
    assert channel_state.payword_root_b64 is not None
