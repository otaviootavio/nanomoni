"""Pytest fixtures for use case tests."""

from __future__ import annotations

from typing import AsyncGenerator
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.domain.shared import IssuerClientFactory, IssuerClientProtocol
from nanomoni.application.issuer.use_cases.registration import RegistrationService
from nanomoni.application.issuer.use_cases.payment_channel import PaymentChannelService
from nanomoni.application.issuer.use_cases.payword_channel import PaywordChannelService
from nanomoni.application.issuer.use_cases.paytree_channel import PaytreeChannelService
from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.application.vendor.use_cases.payword_payment import PaywordPaymentService
from nanomoni.application.vendor.use_cases.paytree_std_payment import (
    PaytreeStdPaymentService,
)
from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)
from nanomoni.crypto.paytree_scheme import (
    PaytreeStdCryptoScheme,
    PaytreeFirstOptCryptoScheme,
)
from nanomoni.infrastructure.vendor.merkle_node_repository_impl import (
    MerkleNodeRepositoryImpl,
)
from nanomoni.crypto.payword_scheme import PaywordCryptoScheme
from tests.fixtures import (
    InMemoryAccountRepository,
    InMemoryIssuerPaymentChannelRepository,
    InMemoryTaskRepository,
    InMemoryUserRepository,
    VendorPaymentRepositories,
    create_vendor_payment_repositories,
    initialize_vendor_payment_repositories,
)
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from tests.use_cases.helpers.vendor_client_adapter import UseCaseVendorClient


# ============================================================================
# Issuer Repository Fixtures
# ============================================================================


@pytest.fixture
async def issuer_account_repository() -> AsyncGenerator[
    InMemoryAccountRepository, None
]:
    repo = InMemoryAccountRepository()
    yield repo
    repo.clear()


@pytest.fixture
async def issuer_payment_channel_repository() -> AsyncGenerator[
    InMemoryIssuerPaymentChannelRepository, None
]:
    repo = InMemoryIssuerPaymentChannelRepository()
    await repo.initialize()
    yield repo
    repo.clear()


# ============================================================================
# Vendor Repository Fixtures
# ============================================================================


@pytest.fixture
async def vendor_payment_repositories() -> AsyncGenerator[
    VendorPaymentRepositories, None
]:
    repos = create_vendor_payment_repositories()
    await initialize_vendor_payment_repositories(repos)
    yield repos
    repos.clear()


@pytest.fixture
async def user_repository() -> AsyncGenerator[InMemoryUserRepository, None]:
    repo = InMemoryUserRepository()
    yield repo
    repo.clear()


@pytest.fixture
async def task_repository() -> AsyncGenerator[InMemoryTaskRepository, None]:
    repo = InMemoryTaskRepository()
    yield repo
    repo.clear()


# ============================================================================
# Key Fixtures
# ============================================================================


@pytest.fixture
def issuer_key_pair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def issuer_private_key_pem(
    issuer_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    private_key, _ = issuer_key_pair
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def issuer_private_key(
    issuer_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> ec.EllipticCurvePrivateKey:
    private_key, _ = issuer_key_pair
    return private_key


# ============================================================================
# Issuer Service Fixtures
# ============================================================================


@pytest.fixture
def registration_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_private_key_pem: str,
) -> RegistrationService:
    return RegistrationService(
        issuer_private_key_pem=issuer_private_key_pem,
        account_repo=issuer_account_repository,
    )


@pytest.fixture
def payment_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaymentChannelService:
    return PaymentChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


@pytest.fixture
def payword_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaywordChannelService:
    return PaywordChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


@pytest.fixture
def paytree_std_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaytreeChannelService:
    return PaytreeChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
        optimization_type=0,
    )


@pytest.fixture
def paytree_first_opt_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaytreeChannelService:
    return PaytreeChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
        optimization_type=1,
    )


# ============================================================================
# Issuer Client Adapter Fixtures
# ============================================================================


@pytest.fixture
def issuer_client(
    registration_service: RegistrationService,
    payment_channel_service: PaymentChannelService,
    payword_channel_service: PaywordChannelService,
    paytree_std_channel_service: PaytreeChannelService,
    paytree_first_opt_channel_service: PaytreeChannelService,
) -> UseCaseIssuerClient:
    return UseCaseIssuerClient(
        registration_service=registration_service,
        payment_channel_service=payment_channel_service,
        payword_channel_service=payword_channel_service,
        paytree_std_channel_service=paytree_std_channel_service,
        paytree_first_opt_channel_service=paytree_first_opt_channel_service,
    )


@pytest.fixture
def issuer_client_factory(
    registration_service: RegistrationService,
    payment_channel_service: PaymentChannelService,
    payword_channel_service: PaywordChannelService,
    paytree_std_channel_service: PaytreeChannelService,
    paytree_first_opt_channel_service: PaytreeChannelService,
) -> IssuerClientFactory:
    def factory() -> IssuerClientProtocol:
        client: IssuerClientProtocol = UseCaseIssuerClient(
            registration_service=registration_service,
            payment_channel_service=payment_channel_service,
            payword_channel_service=payword_channel_service,
            paytree_std_channel_service=paytree_std_channel_service,
            paytree_first_opt_channel_service=paytree_first_opt_channel_service,
        )
        return client

    return factory


# ============================================================================
# Vendor Service Fixtures
# ============================================================================


@pytest.fixture
def vendor_private_key_pem(
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    private_key, _ = vendor_key_pair
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def payment_service(
    vendor_payment_repositories: VendorPaymentRepositories,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaymentService:
    return PaymentService(
        payment_channel_repository=vendor_payment_repositories.signature,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def payword_payment_service(
    vendor_payment_repositories: VendorPaymentRepositories,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaywordPaymentService:
    return PaywordPaymentService(
        payment_repository=vendor_payment_repositories.payment,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        crypto_scheme=PaywordCryptoScheme(),
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def paytree_std_payment_service(
    vendor_payment_repositories: VendorPaymentRepositories,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeStdPaymentService:
    return PaytreeStdPaymentService(
        payment_repository=vendor_payment_repositories.payment,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        crypto_scheme=PaytreeStdCryptoScheme(),
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def paytree_first_opt_payment_service(
    vendor_payment_repositories: VendorPaymentRepositories,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeFirstOptPaymentService:
    return PaytreeFirstOptPaymentService(
        payment_repository=vendor_payment_repositories.payment,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        crypto_scheme=PaytreeFirstOptCryptoScheme(),
        node_repo=MerkleNodeRepositoryImpl(vendor_payment_repositories.store),
        vendor_private_key_pem=vendor_private_key_pem,
    )


# ============================================================================
# Vendor Client Adapter Fixtures
# ============================================================================


@pytest.fixture
def vendor_client(
    payment_service: PaymentService,
    payword_payment_service: PaywordPaymentService,
    paytree_std_payment_service: PaytreeStdPaymentService,
    paytree_first_opt_payment_service: PaytreeFirstOptPaymentService,
    vendor_public_key_der_b64: str,
) -> UseCaseVendorClient:
    return UseCaseVendorClient(
        payment_service=payment_service,
        payword_payment_service=payword_payment_service,
        paytree_std_payment_service=paytree_std_payment_service,
        paytree_first_opt_payment_service=paytree_first_opt_payment_service,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )
