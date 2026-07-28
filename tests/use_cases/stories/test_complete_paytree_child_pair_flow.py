"""Story: PayTree child-pair flow — open, pay via heap-indexed child reveal, settle.

Mirrors test_complete_paytree_first_opt_flow_settle.py but for the child-pair
protocol: payment k reveals the two children of node k (Eytzinger index),
verified against the vendor's already-known hash for node k (starting from
the root). Settlement sends a frontier proof (most recent child pair + outer
siblings up to the root), not a full leaf->root proof.
"""

from __future__ import annotations

import pytest

from nanomoni.application.issuer.dtos import GetPaymentChannelRequestDTO
from tests.e2e.helpers.client_actor import ClientActor
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.mark.asyncio
async def test_paytree_child_pair_full_bfs_sequence_settles_successfully(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    client = ClientActor()

    await issuer_client.register_account(client.public_key_der_b64)
    vendor_pk = await vendor_client.get_public_key()
    await issuer_client.register_account(vendor_pk.public_key_der_b64)

    channel_amount = 10_000
    unit_value = 2
    max_i = 7  # 8-leaf tree -> max_k = 7 internal nodes

    open_request, paytree = client.create_open_channel_request_paytree_child_pair(
        vendor_pk.public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_child_pair_channel(open_request)
    channel_id = channel_response.channel_id
    assert channel_response.paytree_max_i == paytree.max_k

    for k in range(1, paytree.max_k + 1):
        k_val, left_b64, right_b64 = paytree.payment_proof_child_pair(k)
        resp = await vendor_client.receive_paytree_child_pair_payment(
            channel_id, k=k_val, left_b64=left_b64, right_b64=right_b64
        )
        assert resp.channel_id == channel_id
        assert resp.k == k
        assert resp.cumulative_owed_amount == k * unit_value

    await vendor_client.request_channel_settlement_paytree_child_pair(channel_id)

    channel_state = await issuer_client.get_paytree_child_pair_payment_channel(
        GetPaymentChannelRequestDTO(channel_id=channel_id)
    )
    assert channel_state.is_closed is True
    assert channel_state.balance == paytree.max_k * unit_value


@pytest.mark.asyncio
async def test_paytree_child_pair_partial_sequence_settles_with_frontier_proof(
    issuer_client: UseCaseIssuerClient,
    vendor_client: UseCaseVendorClient,
) -> None:
    """Closing mid-sequence must succeed using only the frontier proof (no full leaf proof)."""
    client = ClientActor()

    await issuer_client.register_account(client.public_key_der_b64)
    vendor_pk = await vendor_client.get_public_key()
    await issuer_client.register_account(vendor_pk.public_key_der_b64)

    channel_amount = 10_000
    unit_value = 1
    max_i = 7

    open_request, paytree = client.create_open_channel_request_paytree_child_pair(
        vendor_pk.public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_child_pair_channel(open_request)
    channel_id = channel_response.channel_id

    # Only pay through k=4 (as in the write-up's worked example): the vendor
    # never has a leaf hash yet, but it does have h4's children (h8, h9).
    for k in range(1, 5):
        k_val, left_b64, right_b64 = paytree.payment_proof_child_pair(k)
        await vendor_client.receive_paytree_child_pair_payment(
            channel_id, k=k_val, left_b64=left_b64, right_b64=right_b64
        )

    await vendor_client.request_channel_settlement_paytree_child_pair(channel_id)

    channel_state = await issuer_client.get_paytree_child_pair_payment_channel(
        GetPaymentChannelRequestDTO(channel_id=channel_id)
    )
    assert channel_state.is_closed is True
    assert channel_state.balance == 4 * unit_value
