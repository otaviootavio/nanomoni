"""Story: PayTree first-opt flow — settle succeeds after multiple pruned-proof payments."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from nanomoni.domain.shared import IssuerClientFactory

from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)
from nanomoni.application.shared.paytree_scheme import PaytreeFirstOptCryptoScheme
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


@pytest.fixture
def paytree_first_opt_payment_service_fixture(
    vendor_payment_repositories: VendorPaymentRepositories,
    issuer_client_factory: "IssuerClientFactory",
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeFirstOptPaymentService:
    node_repo = MerkleNodeRepositoryImpl(vendor_payment_repositories.store)
    return PaytreeFirstOptPaymentService(
        payment_repository=vendor_payment_repositories.payment,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        crypto_scheme=PaytreeFirstOptCryptoScheme(),
        node_repo=node_repo,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def vendor_client_first_opt(
    payment_service: PaymentService,
    payword_payment_service: PaywordPaymentService,
    paytree_std_payment_service: PaytreeStdPaymentService,
    paytree_first_opt_payment_service_fixture: PaytreeFirstOptPaymentService,
    vendor_public_key_der_b64: str,
) -> UseCaseVendorClient:
    return UseCaseVendorClient(
        payment_service=payment_service,
        payword_payment_service=payword_payment_service,
        paytree_std_payment_service=paytree_std_payment_service,
        paytree_first_opt_payment_service=paytree_first_opt_payment_service_fixture,
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
    max_i = 128

    open_request, paytree = client.create_open_channel_request_paytree(
        vendor_pk.public_key_der_b64,
        amount=channel_amount,
        unit_value=unit_value,
        max_i=max_i,
    )
    channel_response = await issuer_client.open_paytree_first_opt_channel(open_request)
    channel_id = channel_response.channel_id

    prior_sent_indexes: list[int] = []
    indices = [1, 2, 3, 4, 5, 6, 7]
    for i in indices:
        i_val, leaf_b64, siblings_b64 = paytree.payment_proof_first_opt(
            i, prior_sent_indexes
        )
        prior_sent_indexes.append(i)
        resp = await vendor_client_first_opt.receive_paytree_first_opt_payment(
            channel_id,
            i=i_val,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            paytree_max_i=max_i,
        )
        assert resp.channel_id == channel_id
        assert resp.i == i

    await vendor_client_first_opt.request_channel_settlement_paytree_first_opt(
        channel_id
    )

    channel_state = await issuer_client.get_paytree_channel(channel_id)
    assert channel_state.is_closed is True
    assert channel_state.balance == indices[-1] * unit_value
