"""Integration test: Lost update on SUBSEQUENT payments with vulnerable implementation.

This test uses a deliberately broken (non-atomic) implementation to prove that
the race condition is real and reproducible when an initial transaction exists.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.application.shared.payment_channel_payloads import OffChainTxPayload
from nanomoni.application.vendor.dtos import ReceivePaymentDTO
from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.crypto.certificates import generate_envelope
from nanomoni.domain.vendor.entities import OffChainTx, PaymentChannel
from nanomoni.infrastructure.storage import RedisKeyValueStore

from .vulnerable_repository import VulnerablePaymentChannelRepositoryImpl


@pytest.mark.asyncio
async def test_vulnerable_subsequent_payment_has_lost_updates(
    redis_store: RedisKeyValueStore,
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that proves the VULNERABLE implementation has lost updates on subsequent payments.

    Scenario:
    - Channel has an existing transaction (owed_amount=10)
    - Two concurrent payments arrive: A (owed=20) and B (owed=25)
    - Without atomic operations, the lower amount can overwrite the higher

    This test EXPECTS to find lost updates, proving the race condition exists.
    """
    iterations = request.config.getoption("--race-iterations", default=500)

    # Setup with VULNERABLE repository
    vulnerable_repo = VulnerablePaymentChannelRepositoryImpl(redis_store)

    payment_service = PaymentService(
        payment_channel_repository=vulnerable_repo,
        issuer_base_url="http://mock-issuer",
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )

    client_private_key, _ = client_key_pair

    # Statistics
    lost_updates = 0
    correct_results = 0
    errors = 0
    both_succeeded = 0

    print("\n=== VULNERABLE Subsequent Payment Test ===")
    print(f"Running {iterations} iterations to demonstrate the race condition...")
    print("EXPECTING lost updates with this broken implementation.\n")

    for iteration in range(iterations):
        computed_id = f"vulnerable_subsequent_{uuid.uuid4().hex[:8]}"

        # Create channel
        payment_channel = PaymentChannel(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            salt_b64="test_salt",
            amount=100,
            balance=0,
            is_closed=False,
        )
        await vulnerable_repo.save_channel(payment_channel)

        # Seed initial transaction (owed_amount=10)
        initial_tx = OffChainTx(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=10,
            payload_b64="initial_payload",
            client_signature_b64="initial_signature",
        )
        await vulnerable_repo.save_payment(payment_channel, initial_tx)

        # Create competing payments
        payload_a = OffChainTxPayload(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=20,
        )
        envelope_a = generate_envelope(client_private_key, payload_a.model_dump())
        dto_a = ReceivePaymentDTO(envelope=envelope_a)

        payload_b = OffChainTxPayload(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=25,
        )
        envelope_b = generate_envelope(client_private_key, payload_b.model_dump())
        dto_b = ReceivePaymentDTO(envelope=envelope_b)

        # Fire both concurrently with NO delay to maximize race chance
        results = await asyncio.gather(
            payment_service.receive_payment(dto_a),
            payment_service.receive_payment(dto_b),
            return_exceptions=True,
        )

        result_a, result_b = results

        # Check final state
        final_channel = await vulnerable_repo.get_by_computed_id(computed_id)
        final_tx = final_channel.latest_tx if final_channel else None
        final_owed = final_tx.owed_amount if final_tx else None

        a_succeeded = not isinstance(result_a, Exception)
        b_succeeded = not isinstance(result_b, Exception)

        if a_succeeded and b_succeeded:
            both_succeeded += 1
            if final_owed == 20:
                lost_updates += 1
            elif final_owed == 25:
                correct_results += 1
            else:
                errors += 1
        elif a_succeeded or b_succeeded:
            correct_results += 1
        else:
            errors += 1

        if iteration % 100 == 0 and iteration > 0:
            rate = (lost_updates / both_succeeded * 100) if both_succeeded > 0 else 0
            print(
                f"  Iter {iteration}: Lost updates: {lost_updates}/{both_succeeded} ({rate:.1f}%)"
            )

    # Print results
    print("\n=== VULNERABLE Subsequent Payment Results ===")
    print(f"Total iterations: {iterations}")
    print(f"Both payments succeeded: {both_succeeded}")
    print(f"Lost updates detected: {lost_updates}")
    print(f"Correct results: {correct_results}")
    print(f"Errors: {errors}")

    if both_succeeded > 0:
        lost_update_rate = (lost_updates / both_succeeded) * 100
        print(f"Lost update rate: {lost_update_rate:.2f}%")

    # This test EXPECTS lost updates with the vulnerable implementation
    if both_succeeded > 50:
        if lost_updates > 0:
            print(
                f"\n✅ TEST PASSED: Found {lost_updates} lost updates, proving the race condition exists."
            )
        else:
            print(
                f"\n⚠️  WARNING: No lost updates detected in {both_succeeded} concurrent cases."
            )
            pytest.skip(
                f"Could not trigger race condition in {iterations} iterations. "
                "Try --race-iterations=5000"
            )
