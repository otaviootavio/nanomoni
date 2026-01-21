"""
Regression Tests: First Payment Index Consistency

This module verifies that first payment validation is consistent between
Payword and Paytree modes after fixing the Paytree zero-index bug.

## Summary of Fixes Covered

### Fix 1: Paytree rejects i=0 as first payment
- In Paytree mode, `prev_i = 0` on cache miss, so `i > 0` is required
- This ensures `cumulative_owed_amount >= unit_value` on first payment

### Fix 2: Consistency between Payword and Paytree
- Payword: `prev_k = 0`, so first payment must have `k >= 1`
- Paytree: `prev_i = 0`, so first payment must have `i >= 1`

### Fix 3: Prevent zero-payment settlement
- The attack scenario using `i=0` should now be rejected

## Code References

Payword validation (payword_payment.py:169):
    prev_k = latest_state.k if latest_state else 0

Paytree validation (paytree_payment.py:168):
    prev_i = latest_state.i if latest_state else 0

cumulative_owed_amount calculation (both modes):
    return index * unit_value  # Where index is k or i

## Running These Tests

These are E2E tests that require the full stack to be running:

    docker compose up -d issuer vendor redis-issuer redis-vendor
    pytest tests/bug/ -v
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.fixture
def issuer_client(issuer_base_url: str) -> IssuerTestClient:
    """Create an issuer test client."""
    return IssuerTestClient(issuer_base_url)


@pytest.fixture
def vendor_client(vendor_base_url: str) -> VendorTestClient:
    """Create a vendor test client."""
    return VendorTestClient(vendor_base_url)


class TestPaytreeZeroIndexFix:
    """
    Verifies that Paytree rejects i=0 as the first payment.
    """

    @pytest.mark.asyncio
    async def test_paytree_rejects_i_zero_first_payment(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        FIX: Paytree should reject i=0 as the first payment.
        """
        # Setup: Create client and vendor actors
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        # Register client with issuer (get initial balance)
        await issuer_client.register_account(client.public_key_der_b64)

        # Register vendor with issuer
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        # Open a Paytree channel
        channel_amount = 1000
        unit_value = 10
        max_i = 100

        open_request, paytree = client.create_open_channel_request_paytree(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_i=max_i,
        )

        channel_response = await issuer_client.open_paytree_channel(open_request)
        channel_id = channel_response.channel_id

        # Generate proof for i=0
        i, leaf_b64, siblings_b64 = paytree.payment_proof(i=0)

        response = await vendor_client.receive_paytree_payment_raw(
            channel_id,
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )

        assert response.status_code == 400, (
            f"Expected 400 error for i=0, got {response.status_code}"
        )

        error_detail = response.json().get("detail", "")
        assert (
            "must be increasing" in error_detail.lower() or "i" in error_detail.lower()
        ), f"Expected error about i needing to be increasing, got: {error_detail}"

        print("\n" + "=" * 70)
        print("FIX CONFIRMED: Paytree rejects i=0 as first payment")
        print(f"  - Channel ID: {channel_id}")
        print("  - Attempted i: 0")
        print(f"  - Response status: {response.status_code}")
        print(f"  - Error: {error_detail}")
        print("=" * 70)


class TestPaywordFirstPaymentMinimum:
    """
    Demonstrates that Payword correctly requires k >= 1 for the first payment.

    This is the EXPECTED behavior that Paytree should also follow.
    """

    @pytest.mark.asyncio
    async def test_payword_rejects_k_zero(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        CORRECT BEHAVIOR: Payword rejects k=0 as it's not greater than prev_k=0.

        This test demonstrates the expected behavior that Paytree should also follow.
        """
        # Setup: Create client and vendor actors
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        # Register client with issuer
        await issuer_client.register_account(client.public_key_der_b64)

        # Register vendor with issuer
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        # Open a Payword channel
        channel_amount = 1000
        unit_value = 10
        max_k = 100
        pebble_count = 10

        open_request, payword = client.create_open_channel_request_payword(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_k=max_k,
            pebble_count=pebble_count,
        )

        channel_response = await issuer_client.open_payword_channel(open_request)
        channel_id = channel_response.channel_id

        # Generate token for k=0
        # Note: Payword.payment_proof_b64 allows k=0
        token_b64 = payword.payment_proof_b64(k=0)

        # CORRECT: This should fail because k must be > prev_k (which is 0)
        response = await vendor_client.receive_payword_payment_raw(
            channel_id,
            k=0,
            token_b64=token_b64,
        )

        # Verify correct behavior: k=0 is rejected
        assert response.status_code == 400, (
            f"Expected 400 error for k=0, got {response.status_code}"
        )

        error_detail = response.json().get("detail", "")
        assert (
            "must be increasing" in error_detail.lower() or "k" in error_detail.lower()
        ), f"Expected error about k needing to be increasing, got: {error_detail}"

        print("\n" + "=" * 70)
        print("CORRECT BEHAVIOR: Payword rejects k=0 as first payment")
        print(f"  - Channel ID: {channel_id}")
        print("  - Attempted k: 0")
        print(f"  - Response status: {response.status_code}")
        print(f"  - Error: {error_detail}")
        print("=" * 70)

    @pytest.mark.asyncio
    async def test_payword_accepts_k_one(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        CORRECT BEHAVIOR: Payword accepts k=1 as the minimum first payment.
        """
        # Setup
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        await issuer_client.register_account(client.public_key_der_b64)
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        channel_amount = 1000
        unit_value = 10
        max_k = 100
        pebble_count = 10

        open_request, payword = client.create_open_channel_request_payword(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_k=max_k,
            pebble_count=pebble_count,
        )

        channel_response = await issuer_client.open_payword_channel(open_request)
        channel_id = channel_response.channel_id

        # Generate token for k=1
        token_b64 = payword.payment_proof_b64(k=1)

        # CORRECT: k=1 should be accepted
        response = await vendor_client.receive_payword_payment(
            channel_id,
            k=1,
            token_b64=token_b64,
        )

        assert response.k == 1
        assert response.cumulative_owed_amount == unit_value, (
            f"Expected cumulative_owed_amount={unit_value}, got {response.cumulative_owed_amount}"
        )

        print("\n" + "=" * 70)
        print("CORRECT BEHAVIOR: Payword accepts k=1 as first payment")
        print(f"  - Channel ID: {channel_id}")
        print(f"  - Payment k: {response.k}")
        print(f"  - cumulative_owed_amount: {response.cumulative_owed_amount}")
        print("=" * 70)


class TestConsistencyBetweenModes:
    """
    Verifies Payword and Paytree have consistent minimum first payment behavior.
    """

    @pytest.mark.asyncio
    async def test_first_payment_consistency(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        CONSISTENCY: Payword and Paytree have the same minimum first payment values.
        """
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        await issuer_client.register_account(client.public_key_der_b64)
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        channel_amount = 1000
        unit_value = 10

        # Open Payword channel
        payword_request, payword = client.create_open_channel_request_payword(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_k=100,
            pebble_count=10,
        )
        payword_channel = await issuer_client.open_payword_channel(payword_request)

        # Open Paytree channel (need new client for different channel)
        client2 = ClientActor()
        await issuer_client.register_account(client2.public_key_der_b64)

        paytree_request, paytree = client2.create_open_channel_request_paytree(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_i=100,
        )
        paytree_channel = await issuer_client.open_paytree_channel(paytree_request)

        # Send minimum valid first payment for each mode
        # Payword: k=1 (k=0 is rejected)
        payword_token = payword.payment_proof_b64(k=1)
        payword_response = await vendor_client.receive_payword_payment(
            payword_channel.channel_id,
            k=1,
            token_b64=payword_token,
        )

        # Paytree: i=1 (i=0 is rejected)
        i, leaf_b64, siblings_b64 = paytree.payment_proof(i=1)
        paytree_response = await vendor_client.receive_paytree_payment(
            paytree_channel.channel_id,
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )

        print("\n" + "=" * 70)
        print("CONSISTENCY CONFIRMED")
        print("-" * 70)
        print("Payword:")
        print("  - Minimum first payment index: k=1")
        print(f"  - cumulative_owed_amount: {payword_response.cumulative_owed_amount}")
        print("-" * 70)
        print("Paytree:")
        print("  - Minimum first payment index: i=1")
        print(f"  - cumulative_owed_amount: {paytree_response.cumulative_owed_amount}")
        print("=" * 70)

        assert payword_response.cumulative_owed_amount == unit_value
        assert paytree_response.cumulative_owed_amount == unit_value


class TestSkipPaymentsBug:
    """
    Demonstrates that both Payword and Paytree allow skipping payment indices.

    This may or may not be a bug depending on design intent, but it's worth noting.
    """

    @pytest.mark.asyncio
    async def test_payword_allows_skipping_indices(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        Payword allows sending k=5 as the first payment (skipping k=1,2,3,4).

        This may be intentional (client pays more upfront) but worth documenting.
        """
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        await issuer_client.register_account(client.public_key_der_b64)
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        channel_amount = 1000
        unit_value = 10

        open_request, payword = client.create_open_channel_request_payword(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_k=100,
            pebble_count=10,
        )
        channel = await issuer_client.open_payword_channel(open_request)

        # Skip directly to k=5
        token_b64 = payword.payment_proof_b64(k=5)
        response = await vendor_client.receive_payword_payment(
            channel.channel_id,
            k=5,
            token_b64=token_b64,
        )

        assert response.k == 5
        assert response.cumulative_owed_amount == 5 * unit_value

        print("\n" + "=" * 70)
        print("OBSERVATION: Payword allows skipping indices")
        print("  - First payment k: 5 (skipped 1,2,3,4)")
        print(f"  - cumulative_owed_amount: {response.cumulative_owed_amount}")
        print("=" * 70)

    @pytest.mark.asyncio
    async def test_paytree_allows_skipping_indices(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        Paytree allows sending i=5 as the first payment (skipping i=1,2,3,4).
        """
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        await issuer_client.register_account(client.public_key_der_b64)
        await issuer_client.register_account(vendor_pk.public_key_der_b64)

        channel_amount = 1000
        unit_value = 10

        open_request, paytree = client.create_open_channel_request_paytree(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_i=100,
        )
        channel = await issuer_client.open_paytree_channel(open_request)

        # Skip directly to i=5
        i, leaf_b64, siblings_b64 = paytree.payment_proof(i=5)
        response = await vendor_client.receive_paytree_payment(
            channel.channel_id,
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )

        assert response.i == 5
        assert response.cumulative_owed_amount == 5 * unit_value

        print("\n" + "=" * 70)
        print("OBSERVATION: Paytree allows skipping indices")
        print("  - First payment i: 5 (skipped 1,2,3,4)")
        print(f"  - cumulative_owed_amount: {response.cumulative_owed_amount}")
        print("=" * 70)


class TestSettlementWithZeroPaymentFix:
    """
    Verifies the zero-payment settlement attack is blocked.
    """

    @pytest.mark.asyncio
    async def test_paytree_settlement_rejects_zero_payment(
        self,
        require_services: None,
        issuer_client: IssuerTestClient,
        vendor_client: VendorTestClient,
    ) -> None:
        """
        FIX: Client cannot settle with a zero-payment (i=0) proof.
        """
        client = ClientActor()
        vendor_pk = await vendor_client.get_public_key()

        # Get initial balances
        client_initial = await issuer_client.register_account(client.public_key_der_b64)
        vendor_initial = await issuer_client.register_account(
            vendor_pk.public_key_der_b64
        )

        channel_amount = 1000
        unit_value = 10

        # Open channel (locks client funds)
        open_request, paytree = client.create_open_channel_request_paytree(
            vendor_pk.public_key_der_b64,
            amount=channel_amount,
            unit_value=unit_value,
            max_i=100,
        )
        channel = await issuer_client.open_paytree_channel(open_request)

        # Check client balance after opening (should be reduced by channel_amount)
        client_after_open = await issuer_client.get_account(client.public_key_der_b64)
        assert client_after_open.balance == client_initial.balance - channel_amount

        # Attempt payment with i=0 (should be rejected)
        i, leaf_b64, siblings_b64 = paytree.payment_proof(i=0)
        rejected = await vendor_client.receive_paytree_payment_raw(
            channel.channel_id,
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )
        assert rejected.status_code == 400, (
            f"Expected 400 error for i=0, got {rejected.status_code}"
        )

        # Send valid first payment with i=1
        i, leaf_b64, siblings_b64 = paytree.payment_proof(i=1)
        payment_response = await vendor_client.receive_paytree_payment(
            channel.channel_id,
            i=i,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )

        assert payment_response.cumulative_owed_amount == unit_value

        # Request settlement
        await vendor_client.request_channel_settlement_paytree(channel.channel_id)

        # Wait for settlement to complete
        import asyncio

        for _ in range(10):
            channel_state = await issuer_client.get_paytree_channel(channel.channel_id)
            if channel_state.is_closed:
                break
            await asyncio.sleep(0.5)

        # Check final balances
        client_final = await issuer_client.get_account(client.public_key_der_b64)
        vendor_final = await issuer_client.get_account(vendor_pk.public_key_der_b64)

        # Calculate what happened
        vendor_received = vendor_final.balance - vendor_initial.balance
        client_refund = client_final.balance - client_after_open.balance

        print("\n" + "=" * 70)
        print("FIX CONFIRMED: Settlement with zero payment is blocked")
        print("-" * 70)
        print(f"Channel amount locked: {channel_amount}")
        print(f"Payment sent (i=1): cumulative_owed_amount = {unit_value}")
        print("-" * 70)
        print(f"Vendor received: {vendor_received}")
        print(f"Client refund: {client_refund}")
        print("=" * 70)

        # Assert the fix
        assert vendor_received == unit_value, (
            f"Expected vendor to receive {unit_value}, got {vendor_received}"
        )
        assert client_refund == channel_amount - unit_value, (
            f"Expected client refund of {channel_amount - unit_value}, got {client_refund}"
        )
