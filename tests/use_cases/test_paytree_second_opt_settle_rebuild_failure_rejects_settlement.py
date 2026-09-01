"""Regression: second-opt rejects settlement if the lazy full-proof rebuild fails.

Second-opt inherits first-opt's settle-time lazy rebuild
(``_rebuild_paytree_proof_for_settlement`` / ``rebuild_full_paytree_proof``)
unchanged: a payment is only ever verified against the pruned proof it
carries, and the full leaf->root proof needed for settlement is reconstructed
from the sparse node store at settle time. A missing dependency node there
(should be rare in practice) must reject settlement with a ValueError rather
than silently settling with a wrong or incomplete proof.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from nanomoni.domain.shared import IssuerClientFactory

from nanomoni.application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
)
from nanomoni.application.shared.paytree_scheme import PaytreeSecondOptCryptoScheme
from nanomoni.infrastructure.vendor.merkle_node_repository_impl import (
    MerkleNodeRepositoryImpl,
)
from tests.e2e.helpers.client_actor import ClientActor
from tests.fixtures.in_memory_repositories import VendorPaymentRepositories
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient

from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.application.vendor.use_cases.payword_payment import PaywordPaymentService
from nanomoni.application.vendor.use_cases.paytree_std_payment import (
    PaytreeStdPaymentService,
)


class _DropDependencyMerkleNodeRepository(MerkleNodeRepositoryImpl):
    """Same as MerkleNodeRepositoryImpl, but get_nodes always returns empty.

    receive_payment's own prefetch (get_channel_and_nodes) is untouched, so
    payments verify and persist normally; only the settle-time rebuild --
    which resolves every dependency via get_nodes, with no local shortcut --
    sees a store that appears to hold nothing.
    """

    async def get_nodes(self, channel_id: str, keys: list[str]) -> dict[str, str]:
        return {}


@pytest.fixture
def drop_dependency_node_repo(
    vendor_payment_repositories: VendorPaymentRepositories,
) -> _DropDependencyMerkleNodeRepository:
    return _DropDependencyMerkleNodeRepository(vendor_payment_repositories.store)


@pytest.fixture
def paytree_second_opt_payment_service_with_missing_deps(
    vendor_payment_repositories: VendorPaymentRepositories,
    drop_dependency_node_repo: _DropDependencyMerkleNodeRepository,
    issuer_client_factory: "IssuerClientFactory",
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeSecondOptPaymentService:
    return PaytreeSecondOptPaymentService(
        payment_repository=vendor_payment_repositories.payment,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        crypto_scheme=PaytreeSecondOptCryptoScheme(),
        node_repo=drop_dependency_node_repo,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def vendor_client_second_opt_missing_deps(
    payment_service: PaymentService,
    payword_payment_service: PaywordPaymentService,
    paytree_std_payment_service: PaytreeStdPaymentService,
    paytree_second_opt_payment_service_with_missing_deps: PaytreeSecondOptPaymentService,
    vendor_public_key_der_b64: str,
) -> UseCaseVendorClient:
    return UseCaseVendorClient(
        payment_service=payment_service,
        payword_payment_service=payword_payment_service,
        paytree_std_payment_service=paytree_std_payment_service,
        paytree_first_opt_payment_service=paytree_second_opt_payment_service_with_missing_deps,
        paytree_second_opt_payment_service=paytree_second_opt_payment_service_with_missing_deps,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )


@pytest.mark.asyncio
async def test_second_opt_settle_rejects_when_lazy_rebuild_fails(
    issuer_client: UseCaseIssuerClient,
    vendor_client_second_opt_missing_deps: UseCaseVendorClient,
) -> None:
    client = ClientActor()

    await issuer_client.register_account(client.public_key_der_b64)
    vendor_pk = await vendor_client_second_opt_missing_deps.get_public_key()
    await issuer_client.register_account(vendor_pk.public_key_der_b64)

    max_i = 128
    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_pk.public_key_der_b64,
        amount=10_000,
        unit_value=1,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_second_opt_channel(open_request)
    channel_id = channel_response.channel_id

    # The payment itself verifies and persists fine -- receive_payment's own
    # prefetch (get_channel_and_nodes) isn't touched by the mock.
    i1_val, leaf1_b64, siblings1_b64 = paytree.payment_proof_first_opt(1, [])
    first = (
        await vendor_client_second_opt_missing_deps.receive_paytree_second_opt_payment(
            channel_id,
            i=i1_val,
            leaf_b64=leaf1_b64,
            siblings_b64=siblings1_b64,
            paytree_max_i=max_i,
        )
    )
    assert first.i == 1

    # Settlement's lazy rebuild resolves every full-proof dependency via
    # get_nodes, which the mock always reports empty -- the rebuild must fail
    # and settlement must be rejected, not silently settle with a bad proof.
    with pytest.raises(ValueError, match="No complete PayTree proof available"):
        await vendor_client_second_opt_missing_deps.request_channel_settlement_paytree_second_opt(
            channel_id
        )
