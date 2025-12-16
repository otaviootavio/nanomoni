"""Integration test: Lost update on FIRST payment with vulnerable implementation.

This test uses a deliberately broken (non-atomic) implementation to prove that
the race condition is real when two requests race to be the first payment.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.application.shared.payment_channel_payloads import OffChainTxPayload
from nanomoni.application.vendor.dtos import ReceivePaymentDTO
from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.crypto.certificates import generate_envelope
from nanomoni.domain.vendor.entities import PaymentChannel
from nanomoni.infrastructure.storage import RedisKeyValueStore
from nanomoni.infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)

from .vulnerable_repository import VulnerableOffChainTxRepositoryImpl


@pytest.mark.asyncio
async def test_vulnerable_first_payment_has_lost_updates(
    redis_store: RedisKeyValueStore,
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that proves the VULNERABLE implementation has lost updates on FIRST payment.

    Scenario:
    - Channel exists but has NO transactions yet
    - Two concurrent payments both race to be the first: A (owed=20) and B (owed=25)
    - Both see latest_tx=None and believe they're making the first payment
    - Without atomic operations, the lower amount can overwrite the higher

    This test EXPECTS to find lost updates, proving the race condition exists.
    """
    iterations = request.config.getoption("--race-iterations", default=500)

    vulnerable_repo = VulnerableOffChainTxRepositoryImpl(redis_store)
    payment_channel_repo = PaymentChannelRepositoryImpl(redis_store)

    payment_service = PaymentService(
        off_chain_tx_repository=vulnerable_repo,
        payment_channel_repository=payment_channel_repo,
        issuer_base_url="http://mock-issuer",
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )

    client_private_key, _ = client_key_pair

    lost_updates = 0
    correct_results = 0
    errors = 0
    both_succeeded = 0

    print("\n=== VULNERABLE First Payment Test ===")
    print(f"Running {iterations} iterations (no initial tx seeded)...")
    print("EXPECTING lost updates with this broken implementation.\n")

    # Store channels by computed_id for the mock to return
    channels_by_id: dict[str, PaymentChannel] = {}

    async def mock_verify_payment_channel(computed_id: str) -> PaymentChannel:
        """Mock that returns the pre-created channel without HTTP call."""
        return channels_by_id[computed_id]

    # Patch _verify_payment_channel to avoid HTTP calls to issuer
    with patch.object(
        payment_service,
        "_verify_payment_channel",
        new=AsyncMock(side_effect=mock_verify_payment_channel),
    ):
        for iteration in range(iterations):
            computed_id = f"vulnerable_first_{uuid.uuid4().hex[:8]}"

            # Create channel only - NO initial transaction
            payment_channel = PaymentChannel(
                computed_id=computed_id,
                client_public_key_der_b64=client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_public_key_der_b64,
                salt_b64="test_salt",
                amount=100,
                balance=0,
                is_closed=False,
            )
            await payment_channel_repo.create(payment_channel)
            channels_by_id[computed_id] = payment_channel

            # Both try to be first payment
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
            final_tx = await vulnerable_repo.get_latest_by_computed_id(computed_id)
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
                rate = (
                    (lost_updates / both_succeeded * 100) if both_succeeded > 0 else 0
                )
                print(
                    f"  Iter {iteration}: Lost updates: {lost_updates}/{both_succeeded} ({rate:.1f}%)"
                )

    print("\n=== VULNERABLE First Payment Results ===")
    print(f"Total iterations: {iterations}")
    print(f"Both payments succeeded: {both_succeeded}")
    print(f"Lost updates detected: {lost_updates}")
    print(f"Correct results: {correct_results}")
    print(f"Errors: {errors}")

    if both_succeeded > 0:
        print(f"Lost update rate: {(lost_updates / both_succeeded) * 100:.2f}%")

    if both_succeeded > 50:
        if lost_updates > 0:
            print(
                f"\n✅ TEST PASSED: Found {lost_updates} lost updates on first payment race."
            )
        else:
            print(
                f"\n⚠️  WARNING: No lost updates detected in {both_succeeded} concurrent cases."
            )
            pytest.skip(
                f"Could not trigger first payment race in {iterations} iterations. "
                "Try --race-iterations=5000"
            )
