"""Stress test: Parallel payment streaming with multiple clients - 2 to 32 clients."""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


async def _client_payment_stream(
    client: ClientActor,
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    vendor_public_key_der_b64: str,
    num_payments: int,
    client_id: int,
) -> dict[str, int]:
    """
    Execute payment streaming for a single client.

    Returns:
        Dictionary with client_id, payments_sent, and final_owed_amount
    """
    # Register client
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    # Open payment channel
    channel_amount = 1000000  # Large amount to support many payments
    open_request = client.create_open_channel_request(
        vendor_public_key_der_b64, channel_amount
    )
    channel_response = await issuer_client.open_channel(open_request)
    computed_id = channel_response.computed_id

    assert channel_response.amount == channel_amount
    assert channel_response.balance == 0

    # Send sequential offchain payments
    last_owed_amount = 0
    for payment_number in range(1, num_payments + 1):
        owed_amount = (
            payment_number  # Cumulative owed amount (1, 2, 3, ..., num_payments)
        )
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, owed_amount
        )
        payment_response = await vendor_client.receive_payment(
            computed_id, payment_envelope
        )

        assert payment_response.owed_amount == owed_amount
        assert payment_response.computed_id == computed_id
        assert owed_amount > last_owed_amount

        last_owed_amount = owed_amount

    # Close the channel to settle payments
    await vendor_client.request_channel_closure(computed_id)

    # Verify final state after closure
    channel_state = await issuer_client.get_channel(computed_id)
    assert channel_state.is_closed is True
    assert channel_state.computed_id == computed_id
    assert channel_state.balance == last_owed_amount
    assert channel_state.amount == channel_amount

    return {
        "client_id": client_id,
        "payments_sent": num_payments,
        "final_owed_amount": last_owed_amount,
    }


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("num_clients", [2, 4, 8, 16, 32])
async def test_stress_parallel_payment_streaming_multiple_clients(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    num_clients: int,
) -> None:
    """
    Stress test: Send payments in parallel from multiple clients.

    This test verifies the system can handle concurrent payment streams
    from multiple clients without failures or performance degradation.

    Args:
        num_clients: Number of parallel clients (2, 4, 8, 16, or 32)
    """
    # Setup: Register vendor once (shared across all clients)
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Create multiple client actors
    clients = [ClientActor() for _ in range(num_clients)]

    # Number of payments per client (reduced for parallel execution)
    num_payments_per_client = 100

    print(f"\n[Parallel Payment Streaming] Starting {num_clients} parallel clients")
    print(f"Each client will send {num_payments_per_client} payments")

    # Execute all clients in parallel
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(
        *[
            _client_payment_stream(
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

    # Verify all clients completed successfully
    assert len(results) == num_clients
    total_payments = sum(r["payments_sent"] for r in results)
    total_owed = sum(r["final_owed_amount"] for r in results)

    print("\n[Parallel Payment Streaming] Results:")
    print(f"  Clients: {num_clients}")
    print(f"  Total payments sent: {total_payments}")
    print(f"  Total owed amount: {total_owed}")
    print(f"  Elapsed time: {elapsed_time:.2f}s")
    print(f"  Throughput: {total_payments / elapsed_time:.2f} payments/sec")

    # Verify each client's result
    for result in results:
        assert result["payments_sent"] == num_payments_per_client
        assert result["final_owed_amount"] == num_payments_per_client

    print(
        f"\n[Parallel Payment Streaming] Successfully completed {num_clients} parallel clients"
    )
