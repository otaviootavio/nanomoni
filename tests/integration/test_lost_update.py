"""Integration test for lost update race condition in vendor payment processing.

This test uses real Redis and runs multiple iterations to catch race conditions
statistically through natural concurrency.
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
from nanomoni.infrastructure.vendor.off_chain_tx_repository_impl import (
    OffChainTxRepositoryImpl,
)
from nanomoni.infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)


@pytest.mark.asyncio
async def test_lost_update_race_condition_statistical(
    redis_store: RedisKeyValueStore,
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test lost update race condition using real Redis and statistical iteration.

    This test:
    1. Runs multiple iterations (default 100) of concurrent payment processing
    2. Each iteration sends two payments concurrently: A (owed=20) and B (owed=25)
    3. Tracks how many times the lost update occurs (final value is 20 instead of 25)
    4. Reports statistics on race condition frequency

    The test demonstrates that without proper concurrency control, lost updates
    can occur when two payments are processed simultaneously.

    Usage:
        pytest tests/integration/test_lost_update.py --race-iterations=200
        pytest tests/integration/test_lost_update.py --race-iterations=1000 --min-lost-updates=5
    """
    # Configuration
    iterations = request.config.getoption("--race-iterations", default=1000)
    min_lost_updates_expected = request.config.getoption("--min-lost-updates", default=0)

    # Setup repositories
    off_chain_tx_repo = OffChainTxRepositoryImpl(redis_store)
    payment_channel_repo = PaymentChannelRepositoryImpl(redis_store)

    # Create PaymentService
    payment_service = PaymentService(
        off_chain_tx_repository=off_chain_tx_repo,
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
    # Goal: Maintain Lost Update Rate at 50% (0.5)
    # Variable: Delay (seconds). Positive = Delay B, Negative = Delay A.
    current_delay = 0.0
    
    # Controller Gains
    # Start with a larger Kp for exploration, then reduce when we cross zero
    initial_Kp = 0.001
    Kp = initial_Kp
    Ki = 0.0001
    
    integral_error = 0.0
    
    # Dynamic Gain Logic
    # We monitor zero crossings of the delay signal (sign changes)
    # When sign changes, it means we passed the "balance point" (approx 0.0s delay usually)
    # We reduce Kp to fine-tune.
    prev_delay_sign = 0 # 0=Init, 1=Pos, -1=Neg
    gain_reduction_factor = 0.5 # Reduce by 50% on each crossing
    min_Kp = 0.00005 # Minimum step size (50us)
    
    delay_history: list[float] = []
    
    print(f"\n=== Lost Update Statistical Test (Adaptive PI + Dynamic Gain) ===")
    print(f"Running {iterations} iterations with PI controller targeting 50% race rate...")
    print(f"Initial Kp={Kp}, Dynamic Gain Scheduling Enabled")

    for iteration in range(iterations):
        # Generate unique channel ID for this iteration
        computed_id = f"test_channel_{uuid.uuid4().hex[:8]}"

        # Create a fresh payment channel for this iteration
        payment_channel = PaymentChannel(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            salt_b64="test_salt",
            amount=100,  # Channel has 100 units
            balance=0,
            is_closed=False,
        )

        # Seed the repository with the channel
        await payment_channel_repo.create(payment_channel)

        # Create initial transaction with owed_amount=10
        initial_tx = OffChainTx(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=10,
            payload_b64="initial_payload",
            client_signature_b64="initial_signature",
        )
        await off_chain_tx_repo.create(initial_tx)

        # Create two payment envelopes
        # Payload A: owed=20
        payload_a = OffChainTxPayload(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=20,
        )
        envelope_a = generate_envelope(client_private_key, payload_a.model_dump())
        dto_a = ReceivePaymentDTO(envelope=envelope_a)

        # Payload B: owed=25 (higher than A)
        payload_b = OffChainTxPayload(
            computed_id=computed_id,
            client_public_key_der_b64=client_public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=25,
        )
        envelope_b = generate_envelope(client_private_key, payload_b.model_dump())
        dto_b = ReceivePaymentDTO(envelope=envelope_b)

        # Process both payments concurrently with adaptive delay
        # We control the start time of tasks to target the race condition
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
        final_tx = await off_chain_tx_repo.get_latest_by_computed_id(computed_id)
        final_owed = final_tx.owed_amount if final_tx else None

        # Analyze results
        a_succeeded = not isinstance(result_a, Exception)
        b_succeeded = not isinstance(result_b, Exception)

        # Adaptive Control Logic (PI Controller)
        # Target: Lost Update Rate = 0.5 (50%)
        # If Outcome=Lost (1) -> Rate is too high locally -> need to decrease rate.
        #   To decrease Lost (A last), we need to make B last (Correct).
        #   To make B last, B needs to be later relative to A.
        #   B later = Increase Delay (Positive).
        #   Error = (Outcome - Target). If Outcome=1, Error=0.5. Delay += K*0.5 (Increase). Correct.
        # If Outcome=Correct (0) -> Rate is too low locally -> need to increase rate.
        #   To increase Lost (A last), A needs to be later relative to B.
        #   A later = Decrease Delay (Negative).
        #   Error = (Outcome - Target). If Outcome=0, Error=-0.5. Delay += K*(-0.5) (Decrease). Correct.
        
        step_outcome = 0.0
        
        if a_succeeded and b_succeeded:
            both_succeeded += 1
            if final_owed == 20: # Lost Update (A wins last)
                lost_updates += 1
                step_outcome = 1.0 # "High" value
            elif final_owed == 25: # Correct (B wins last)
                correct_results += 1
                step_outcome = 0.0 # "Low" value
            else:
                errors += 1
                # If unexpected, don't change control variable or treat as 0.5 (neutral)
                step_outcome = 0.5
        elif a_succeeded:
            # B failed. B was too late (saw A).
            # We want to make B earlier (Decrease Delay).
            # This is equivalent to "Correct" outcome bias (pushing towards negative/lower delay)
            # Treat as outcome 0.0 (Correct/B-like side)
            correct_results += 1
            step_outcome = 0.0
        elif b_succeeded:
            # A failed. A was too late (saw B).
            # We want to make A earlier (Increase Delay).
            # This is equivalent to "Lost" outcome bias (pushing towards positive/higher delay)
            # Treat as outcome 1.0
            correct_results += 1
            step_outcome = 1.0
        else:
            errors += 1
            step_outcome = 0.5

        # Calculate Error
        error = step_outcome - 0.5
        
        # Update Integral
        integral_error += error
        
        # Clamp integral to prevent windup (optional, but good practice)
        integral_error = max(-100.0, min(100.0, integral_error))

        # PI Update
        # Using dynamic Kp
        current_delay += (Kp * error) + (Ki * integral_error)
        
        # Dynamic Gain Scheduling (Zero Crossing Detection)
        # Check if delay sign changed (Zero Crossing detected)
        # We use a small threshold to avoid noise around 0 exactly
        current_sign = 0
        if current_delay > 1e-6:
            current_sign = 1
        elif current_delay < -1e-6:
            current_sign = -1
            
        if prev_delay_sign != 0 and current_sign != 0 and current_sign != prev_delay_sign:
            # Sign changed! We crossed the "root".
            # Reduce Kp to refine search
            old_Kp = Kp
            Kp = max(min_Kp, Kp * gain_reduction_factor)
            if Kp < old_Kp:
                print(f"  [Auto-Tune] Zero crossing detected at Iter {iteration}. Reducing Kp: {old_Kp:.6f} -> {Kp:.6f}")
        
        if current_sign != 0:
            prev_delay_sign = current_sign
            
        delay_history.append(current_delay)

        if iteration % 50 == 0:
            avg_delay = sum(delay_history[-50:]) / len(delay_history[-50:]) if delay_history else 0
            current_rate = (lost_updates / both_succeeded * 100) if both_succeeded > 0 else 0
            print(
                f"  Iter {iteration}: Delay={current_delay*1000:.3f}ms (Avg: {avg_delay*1000:.3f}ms), "
                f"Rate={current_rate:.1f}% ({lost_updates}/{both_succeeded})"
            )

    # Print statistics
    print(f"\n=== Test Results ===")
    print(f"Total iterations: {iterations}")
    print(f"Both payments succeeded: {both_succeeded}")
    print(f"Lost updates detected: {lost_updates}")
    print(f"Correct results: {correct_results}")
    print(f"Errors/unexpected: {errors}")
    if both_succeeded > 0:
        lost_update_rate = (lost_updates / both_succeeded) * 100
        print(f"Lost update rate: {lost_update_rate:.2f}% (when both succeeded)")
        print(
            f"\nNote: Lost updates occur when both payments succeed but the final "
            f"value is 20 (lower) instead of 25 (higher). "
            f"This indicates a race condition where the higher payment was overwritten."
        )
    else:
        print(
            "\nNote: No cases where both payments succeeded. "
            "This suggests proper validation is preventing concurrent updates."
        )

    # Assertions - make them informative rather than strict
    if min_lost_updates_expected > 0:
        assert (
            lost_updates >= min_lost_updates_expected
        ), (
            f"Expected at least {min_lost_updates_expected} lost updates, "
            f"but only found {lost_updates} out of {both_succeeded} cases where both succeeded. "
            "This may indicate:\n"
            "  1. The race condition is very rare and needs more iterations\n"
            "  2. The race condition was fixed\n"
            "  3. The timing doesn't favor the race condition\n"
            f"Try running with --race-iterations={iterations * 10} for better statistics."
        )

    # Informative assertion about the test results
    if both_succeeded > 100 and lost_updates == 0:
        print(
            f"\n⚠️  WARNING: Ran {iterations} iterations with {both_succeeded} cases "
            "where both payments succeeded, but no lost updates were detected. "
            "This suggests the race condition may be very rare or the implementation "
            "has some protection against it."
        )
