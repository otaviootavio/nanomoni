"""Stress test: Parallel PayTree payment streaming with multiple clients - 2 to 32 clients."""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


async def _client_paytree_payment_stream(
    client: ClientActor,
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    vendor_public_key_der_b64: str,
    num_payments: int,
    client_id: int,
) -> dict[str, int]:
    """
    Execute PayTree payment streaming for a single client.

    Returns:
        Dictionary with client_id, payments_sent, and final_i
    """
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    unit_value = 1
    max_i = num_payments
    channel_amount = 1000000

    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_channel(open_request)
    computed_id = channel_response.computed_id

    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0
    assert channel_response.paytree_root_b64 is not None

    last_i = 0
    for i in range(1, num_payments + 1):
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof(i=i)
        resp = await vendor_client.receive_paytree_payment(
            computed_id, i=i_val, leaf_b64=leaf_b64, siblings_b64=siblings_b64
        )
        assert resp.i == i
        assert resp.owed_amount == i * unit_value
        assert i > last_i
        last_i = i

    await vendor_client.request_channel_closure_paytree(computed_id)

    channel_state = await issuer_client.get_paytree_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == last_i * unit_value
    assert channel_state.amount == channel_amount

    return {
        "client_id": client_id,
        "payments_sent": num_payments,
        "final_i": last_i,
    }


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("num_clients", [2, 4, 8, 16, 32])
async def test_stress_parallel_paytree_payment_streaming_multiple_clients(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    num_clients: int,
) -> None:
    """
    Stress test: Send PayTree payments in parallel from multiple clients.
    """
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    clients = [ClientActor() for _ in range(num_clients)]
    num_payments_per_client = 100

    print(
        f"\n[Parallel PayTree Payment Streaming] Starting {num_clients} parallel clients"
    )
    print(f"Each client will send {num_payments_per_client} PayTree payments")

    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(
        *[
            _client_paytree_payment_stream(
                client,
                issuer_client,
                vendor_client,
                vendor_public_key_der_b64,
                num_payments_per_client,
                client_id=i,
            )
            for i, client in enumerate(clients)
        ]
    )
    end_time = asyncio.get_event_loop().time()
    elapsed_time = end_time - start_time

    assert len(results) == num_clients
    total_payments = sum(r["payments_sent"] for r in results)

    print("\n[Parallel PayTree Payment Streaming] Results:")
    print(f"  Clients: {num_clients}")
    print(f"  Total payments sent: {total_payments}")
    print(f"  Elapsed time: {elapsed_time:.2f}s")
    print(f"  Throughput: {total_payments / elapsed_time:.2f} payments/sec")

    for result in results:
        assert result["payments_sent"] == num_payments_per_client
        assert result["final_i"] == num_payments_per_client

    print(
        f"\n[Parallel PayTree Payment Streaming] Successfully completed {num_clients} parallel clients"
    )
