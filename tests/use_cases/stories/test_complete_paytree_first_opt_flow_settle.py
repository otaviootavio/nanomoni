"""Story: PayTree first-opt flow — settle succeeds by loading channel from first-opt store.

This test would fail before the fix that loads the channel (with last_leaf_index /
last_leaf_b64) from the first-opt repository at settle time. Without that fix,
the main payment_channel_repository only has the channel from the first
save_channel() call (before last_leaf was set), so _rebuild_full_paytree_state_
from_first_opt gets a channel with last_leaf_index=None and returns None,
leading to "No PayTree payments received for this channel".

We use a separate store for the first-opt repo so the main paytree repo never
sees the updated channel; the fix loads it from the first-opt store at settle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

import pytest

if TYPE_CHECKING:
    from nanomoni.domain.shared import IssuerClientFactory
    from nanomoni.application.vendor.use_cases.payment import PaymentService
    from nanomoni.application.vendor.use_cases.payword_payment import (
        PaywordPaymentService,
    )
    from tests.fixtures.in_memory_repositories import VendorPaymentRepositories

from nanomoni.application.vendor.use_cases.paytree_payment import PaytreePaymentService
from nanomoni.infrastructure.vendor.paytree_first_opt_repository_impl import (
    PaytreeFirstOptNodeRepositoryImpl,
)
from tests.e2e.helpers.client_actor import ClientActor
from tests.fixtures.in_memory_repositories import (
    _register_vendor_scripts,
)
from tests.fixtures.in_memory_storage import InMemoryKeyValueStore
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


@pytest.fixture
async def first_opt_store() -> AsyncGenerator[InMemoryKeyValueStore, None]:
    """Separate store for first-opt repo so main paytree repo has stale channel at settle."""
    store = InMemoryKeyValueStore()
    await _register_vendor_scripts(store)
    yield store
    store.clear()


@pytest.fixture
def paytree_payment_service_with_first_opt(
    vendor_payment_repositories: "VendorPaymentRepositories",
    issuer_client_factory: "IssuerClientFactory",
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
    first_opt_store: InMemoryKeyValueStore,
) -> PaytreePaymentService:
    """PayTree payment service with first-opt repo on a separate store."""
    first_opt_repo = PaytreeFirstOptNodeRepositoryImpl(first_opt_store)
    return PaytreePaymentService(
        payment_channel_repository=vendor_payment_repositories.paytree,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
        paytree_first_opt_node_repository=first_opt_repo,
    )


@pytest.fixture
def vendor_client_first_opt(
    payment_service: "PaymentService",
    payword_payment_service: "PaywordPaymentService",
    paytree_payment_service_with_first_opt: PaytreePaymentService,
    vendor_public_key_der_b64: str,
) -> UseCaseVendorClient:
    """Vendor client that uses PayTree service with first-opt repo (separate store)."""
    return UseCaseVendorClient(
        payment_service=payment_service,
        payword_payment_service=payword_payment_service,
        paytree_payment_service=paytree_payment_service_with_first_opt,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )


@pytest.mark.asyncio
async def test_paytree_first_opt_settle_succeeds_when_channel_in_first_opt_store_only(
    issuer_client: UseCaseIssuerClient,
    vendor_client_first_opt: UseCaseVendorClient,
) -> None:
    """
    First-opt flow: payments stored only in first-opt repo; settle loads channel
    from first-opt store and rebuilds proof. Without the fix this raises
    "No PayTree payments received for this channel".
    """
    client = ClientActor()

    await issuer_client.register_account(client.public_key_der_b64)
    vendor_pk = await vendor_client_first_opt.get_public_key()
    await issuer_client.register_account(vendor_pk.public_key_der_b64)

    channel_amount = 10_000
    unit_value = 1
    # Bigger tree (depth 7): pruned proofs for consecutive payments stop near the leaf,
    # so we rely on stored leaf hashes + build_node_from_dependencies to rebuild at settle.
    # Without storing (0, i) -> leaf_b64 per payment, rebuild would fail with KeyError.
    max_i = 128

    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_pk.public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
        paytree_optimization_type=1,
    )
    channel_response = await issuer_client.open_paytree_channel(open_request)
    channel_id = channel_response.channel_id

    prior_sent_indexes: list[int] = []
    # Consecutive payments so pruned proof is short (LCA with prior is near leaf).
    # Rebuild at settle needs leaf hashes for dependency_indexes; this would fail
    # without the vendor storing (0, i) -> leaf_b64 per payment.
    indices = [1, 2, 3, 4, 5, 6, 7]
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(
            i, prior_sent_indexes
        )
        prior_sent_indexes.append(i)
        resp = await vendor_client_first_opt.receive_paytree_payment(
            channel_id,
            i=i_val,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            optimization_type=1,
            paytree_max_i=max_i,
        )
        assert resp.channel_id == channel_id
        assert resp.i == i

    # Settle: rebuilds full proof from first-opt store (leaf hashes + pruned siblings).
    await vendor_client_first_opt.request_channel_settlement_paytree(channel_id)

    channel_state = await issuer_client.get_paytree_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == indices[-1] * unit_value
