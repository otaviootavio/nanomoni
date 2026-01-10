"""Stress test: Parallel channel lifecycle with multiple clients - 2 to 32 clients."""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


async def _client_channel_lifecycle(
    client: ClientActor,
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    vendor_public_key_der_b64: str,
    num_iterations: int,
    client_id: int,
) -> dict[str, int]:
    """
    Execute channel lifecycle cycles for a single client.

    Returns:
        Dictionary with client_id, iterations_completed, and total_payments
    """
    # Register client
    registration_response = await issuer_client.register_account(
        client.public_key_der_b64
    )
    assert registration_response.client_public_key_der_b64 == client.public_key_der_b64
    assert registration_response.balance > 0

    channel_amount = 1000
    payment_amount = 100
    iterations_completed = 0
    total_payments = 0

    for iteration in range(1, num_iterations + 1):
        # 1. Open payment channel
        open_request = client.create_open_channel_request(
            vendor_public_key_der_b64, channel_amount
        )
        channel_response = await issuer_client.open_channel(open_request)
        computed_id = channel_response.computed_id

        assert channel_response.amount == channel_amount
        assert channel_response.balance == 0
        assert channel_response.client_public_key_der_b64 == client.public_key_der_b64
        assert channel_response.vendor_public_key_der_b64 == vendor_public_key_der_b64

        # 2. Make one payment
        payment_envelope = client.create_payment_envelope(
            computed_id, vendor_public_key_der_b64, payment_amount
        )
        payment_response = await vendor_client.receive_payment(
            computed_id, payment_envelope
        )

        assert payment_response.owed_amount == payment_amount
        assert payment_response.computed_id == computed_id

        # 3. Request channel closure
        await vendor_client.request_channel_closure(computed_id)

        # Verify channel is closed with correct balance
        channel_state = await issuer_client.get_channel(computed_id)
        assert channel_state.is_closed is True
        assert channel_state.balance == payment_amount
        assert channel_state.computed_id == computed_id
        assert channel_state.amount == channel_amount

        iterations_completed += 1
        total_payments += 1

    return {
        "client_id": client_id,
        "iterations_completed": iterations_completed,
        "total_payments": total_payments,
    }


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("num_clients", [2, 4, 8, 16, 32])
async def test_stress_parallel_channel_lifecycle_multiple_clients(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
    num_clients: int,
) -> None:
    """
    Stress test: Perform channel lifecycle operations in parallel from multiple clients.

    This test verifies the system can handle concurrent channel open->payment->close
    cycles from multiple clients without failures or performance degradation.

    Args:
        num_clients: Number of parallel clients (2, 4, 8, 16, or 32)
    """
    # Setup: Register vendor once (shared across all clients)
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Create multiple client actors
    clients = [ClientActor() for _ in range(num_clients)]

    # Number of iterations per client (reduced for parallel execution)
    num_iterations_per_client = 50

    print(f"\n[Parallel Channel Lifecycle] Starting {num_clients} parallel clients")
    print(f"Each client will perform {num_iterations_per_client} channel cycles")

    # Execute all clients in parallel
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(
        *[
            _client_channel_lifecycle(
                client,
                issuer_client,
                vendor_client,
                vendor_public_key_der_b64,
                num_iterations_per_client,
                client_id=i,
            )
            for i, client in enumerate(clients)
        ]
    )
    end_time = asyncio.get_event_loop().time()
    elapsed_time = end_time - start_time

    # Verify all clients completed successfully
    assert len(results) == num_clients
    total_iterations = sum(r["iterations_completed"] for r in results)
    total_payments = sum(r["total_payments"] for r in results)

    print("\n[Parallel Channel Lifecycle] Results:")
    print(f"  Clients: {num_clients}")
    print(f"  Total channel cycles: {total_iterations}")
    print(f"  Total payments: {total_payments}")
    print(f"  Elapsed time: {elapsed_time:.2f}s")
    print(f"  Throughput: {total_iterations / elapsed_time:.2f} cycles/sec")

    # Verify each client's result
    for result in results:
        assert result["iterations_completed"] == num_iterations_per_client
        assert result["total_payments"] == num_iterations_per_client

    print(
        f"\n[Parallel Channel Lifecycle] Successfully completed {num_clients} parallel clients"
    )
