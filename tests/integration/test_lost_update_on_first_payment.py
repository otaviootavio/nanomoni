"""Integration test for lost update race condition on FIRST payment.

This test verifies that when two concurrent requests both try to make the
first payment on a channel, the race condition is handled correctly.
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

from .adaptive_delay_controller import AdaptiveDelayController


@pytest.mark.asyncio
async def test_lost_update_on_first_payment_statistical(
    redis_store: RedisKeyValueStore,
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test lost update race condition on FIRST payment using real Redis.

    This test differs from test_lost_update_race_condition_statistical in that:
    - NO initial transaction is seeded
    - Both payments A (owed=20) and B (owed=25) race to be the FIRST payment
    - This tests the `if not current_raw then SET` branch in the Lua script

    The test verifies that even when both requests think they're making the
    first payment (because both see latest_tx=None in Python), the atomic
    Lua script ensures:
    1. Only one can take the "first payment" path
    2. The second must go through the comparison logic
    3. The higher amount always wins (no lost update)

    Usage:
        pytest tests/integration/test_lost_update_on_first_payment.py --race-iterations=1000
    """
    # Configuration
    iterations = request.config.getoption("--race-iterations", default=1000)
    min_lost_updates_expected = request.config.getoption(
        "--min-lost-updates", default=0
    )

    # Setup repositories
    payment_channel_repo = PaymentChannelRepositoryImpl(redis_store)

    # Create PaymentService
    payment_service = PaymentService(
        payment_channel_repository=payment_channel_repo,
        issuer_base_url="http://mock-issuer",  # Not used since we pre-create channels
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )

    # Crypto setup
    client_private_key, _ = client_key_pair

    # Statistics tracking
    lost_updates = 0
    correct_results = 0
    errors = 0
    both_succeeded = 0

    # Adaptive Control (PI Controller with Dynamic Gain)
    controller = AdaptiveDelayController()

    print("\n=== First Payment Lost Update Statistical Test (Adaptive PI) ===")
    print(
        f"Running {iterations} iterations with PI controller targeting 50% race rate..."
    )
    print("NOTE: No initial transaction seeded - both payments race for FIRST payment")
    print(f"Initial Kp={controller.kp}, Dynamic Gain Scheduling Enabled")

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
            # Generate unique channel ID for this iteration
            computed_id = f"test_first_payment_{uuid.uuid4().hex[:8]}"

            # Create a fresh payment channel for this iteration
            # NOTE: We only create the channel, NOT an initial transaction
            payment_channel = PaymentChannel(
                computed_id=computed_id,
                client_public_key_der_b64=client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_public_key_der_b64,
                salt_b64="test_salt",
                amount=100,  # Channel has 100 units
                balance=0,
                is_closed=False,
            )

            # Seed the repository with the channel ONLY (no initial transaction)
            await payment_channel_repo.save_channel(payment_channel)
            channels_by_id[computed_id] = payment_channel

            # Create two payment envelopes - both trying to be the FIRST payment
            # Payload A: owed=20 (first payment attempt)
            payload_a = OffChainTxPayload(
                computed_id=computed_id,
                client_public_key_der_b64=client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_public_key_der_b64,
                owed_amount=20,
            )
            envelope_a = generate_envelope(client_private_key, payload_a.model_dump())
            dto_a = ReceivePaymentDTO(envelope=envelope_a)

            # Payload B: owed=25 (first payment attempt, higher than A)
            payload_b = OffChainTxPayload(
                computed_id=computed_id,
                client_public_key_der_b64=client_public_key_der_b64,
                vendor_public_key_der_b64=vendor_public_key_der_b64,
                owed_amount=25,
            )
            envelope_b = generate_envelope(client_private_key, payload_b.model_dump())
            dto_b = ReceivePaymentDTO(envelope=envelope_b)

            # Process both payments concurrently with adaptive delay
            current_delay = controller.current_delay
            if current_delay >= 0:
                # Positive delay: Start A first, then B
                task_a = asyncio.create_task(payment_service.receive_payment(dto_a))
                if current_delay > 0:
                    await asyncio.sleep(current_delay)
                task_b = asyncio.create_task(payment_service.receive_payment(dto_b))
            else:
                # Negative delay: Start B first, then A
                task_b = asyncio.create_task(payment_service.receive_payment(dto_b))
                await asyncio.sleep(abs(current_delay))
                task_a = asyncio.create_task(payment_service.receive_payment(dto_a))

            results = await asyncio.gather(
                task_a,
                task_b,
                return_exceptions=True,
            )

            result_a, result_b = results

            # Check final state
            final_channel = await payment_channel_repo.get_by_computed_id(computed_id)
            final_tx = final_channel.latest_tx if final_channel else None
            final_owed = final_tx.owed_amount if final_tx else None

            # Analyze results
            a_succeeded = not isinstance(result_a, Exception)
            b_succeeded = not isinstance(result_b, Exception)

            # Analyze results and determine step outcome for controller
            step_outcome = 0.0

            if a_succeeded and b_succeeded:
                both_succeeded += 1
                if final_owed == 20:  # Lost Update (A wins last)
                    lost_updates += 1
                    step_outcome = 1.0
                elif final_owed == 25:  # Correct (B wins last)
                    correct_results += 1
                    step_outcome = 0.0
                else:
                    errors += 1
                    step_outcome = 0.5
            elif a_succeeded:
                # B failed - B was rejected (saw A's payment)
                correct_results += 1
                step_outcome = 0.0
            elif b_succeeded:
                # A failed - A was rejected (saw B's payment)
                correct_results += 1
                step_outcome = 1.0
            else:
                errors += 1
                step_outcome = 0.5

            # Update controller
            controller.update(step_outcome, iteration)

            if iteration % 50 == 0:
                current_rate = (
                    (lost_updates / both_succeeded * 100) if both_succeeded > 0 else 0
                )
                print(
                    f"  Iter {iteration}: Delay={controller.current_delay * 1000:.3f}ms "
                    f"(Avg: {controller.avg_delay() * 1000:.3f}ms), "
                    f"Rate={current_rate:.1f}% ({lost_updates}/{both_succeeded})"
                )

    # Print statistics
    print("\n=== First Payment Test Results ===")
    print(f"Total iterations: {iterations}")
    print(f"Both payments succeeded: {both_succeeded}")
    print(f"Lost updates detected: {lost_updates}")
    print(f"Correct results: {correct_results}")
    print(f"Errors/unexpected: {errors}")
    if both_succeeded > 0:
        lost_update_rate = (lost_updates / both_succeeded) * 100
        print(f"Lost update rate: {lost_update_rate:.2f}% (when both succeeded)")
        print(
            "\nNote: Lost updates occur when both FIRST payments succeed but the final "
            "value is 20 (lower) instead of 25 (higher). "
            "This would indicate a race condition in the 'first payment' code path."
        )
    else:
        print(
            "\nNote: No cases where both payments succeeded. "
            "This suggests proper validation is preventing concurrent first payments."
        )

    # Assertions
    if min_lost_updates_expected > 0:
        assert lost_updates >= min_lost_updates_expected, (
            f"Expected at least {min_lost_updates_expected} lost updates, "
            f"but only found {lost_updates}. "
            f"Try running with --race-iterations={iterations * 10}"
        )

    # Success assertion: no lost updates should occur with atomic Lua script
    if both_succeeded > 100:
        assert lost_updates == 0, (
            f"CRITICAL: Found {lost_updates} lost updates out of {both_succeeded} cases "
            f"where both first payments succeeded. This indicates the atomic Lua script "
            f"is NOT properly handling the first payment race condition!"
        )
        print(
            f"\n✅ SUCCESS: Ran {iterations} iterations with {both_succeeded} cases "
            "where both first payments succeeded, and NO lost updates were detected. "
            "The atomic Lua script correctly handles the first payment race condition."
        )
