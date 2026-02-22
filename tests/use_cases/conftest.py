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
from nanomoni.application.issuer.use_cases.paytree_first_opt_channel import (
    PaytreeFirstOptChannelService,
)
from nanomoni.application.issuer.use_cases.paytree_second_opt_channel import (
    PaytreeSecondOptChannelService,
)
from nanomoni.application.vendor.use_cases.payment import PaymentService
from nanomoni.application.vendor.use_cases.payword_payment import PaywordPaymentService
from nanomoni.application.vendor.use_cases.paytree_payment import PaytreePaymentService
from nanomoni.application.vendor.use_cases.paytree_first_opt_payment import (
    PaytreeFirstOptPaymentService,
)
from nanomoni.application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
)
from tests.fixtures import (
    InMemoryPaymentChannelRepository,
    InMemoryUserRepository,
    InMemoryTaskRepository,
    InMemoryAccountRepository,
    InMemoryIssuerPaymentChannelRepository,
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
    """Create an in-memory issuer account repository."""
    repo = InMemoryAccountRepository()
    yield repo
    repo.clear()


@pytest.fixture
async def issuer_payment_channel_repository() -> AsyncGenerator[
    InMemoryIssuerPaymentChannelRepository, None
]:
    """Create an in-memory issuer payment channel repository."""
    repo = InMemoryIssuerPaymentChannelRepository()
    await repo.initialize()
    yield repo
    repo.clear()


# ============================================================================
# Vendor Repository Fixtures
# ============================================================================


@pytest.fixture
async def payment_channel_repository() -> AsyncGenerator[
    InMemoryPaymentChannelRepository, None
]:
    """Create an in-memory payment channel repository."""
    repo = InMemoryPaymentChannelRepository()
    await repo.initialize()
    yield repo
    repo.clear()


@pytest.fixture
async def user_repository() -> AsyncGenerator[InMemoryUserRepository, None]:
    """Create an in-memory user repository."""
    repo = InMemoryUserRepository()
    yield repo
    repo.clear()


@pytest.fixture
async def task_repository() -> AsyncGenerator[InMemoryTaskRepository, None]:
    """Create an in-memory task repository."""
    repo = InMemoryTaskRepository()
    yield repo
    repo.clear()


# ============================================================================
# Key Fixtures
# ============================================================================


@pytest.fixture
def issuer_key_pair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """Generate an issuer key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def issuer_private_key_pem(
    issuer_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    """Get issuer private key as PEM string."""
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
    """Get issuer private key."""
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
    """Create a registration service for testing."""
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
    """Create a payment channel service for testing."""
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
    """Create a PayWord channel service for testing."""
    return PaywordChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


@pytest.fixture
def paytree_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaytreeChannelService:
    """Create a PayTree channel service for testing."""
    return PaytreeChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


@pytest.fixture
def paytree_first_opt_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaytreeFirstOptChannelService:
    """Create a PayTree First Opt channel service for testing."""
    return PaytreeFirstOptChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


@pytest.fixture
def paytree_second_opt_channel_service(
    issuer_account_repository: InMemoryAccountRepository,
    issuer_payment_channel_repository: InMemoryIssuerPaymentChannelRepository,
    issuer_private_key: ec.EllipticCurvePrivateKey,
) -> PaytreeSecondOptChannelService:
    """Create a PayTree Second Opt channel service for testing."""
    return PaytreeSecondOptChannelService(
        account_repo=issuer_account_repository,
        channel_repo=issuer_payment_channel_repository,
        issuer_private_key=issuer_private_key,
    )


# ============================================================================
# Issuer Client Adapter Fixtures
# ============================================================================


@pytest.fixture
def issuer_client(
    registration_service: RegistrationService,
    payment_channel_service: PaymentChannelService,
    payword_channel_service: PaywordChannelService,
    paytree_channel_service: PaytreeChannelService,
    paytree_first_opt_channel_service: PaytreeFirstOptChannelService,
    paytree_second_opt_channel_service: PaytreeSecondOptChannelService,
) -> UseCaseIssuerClient:
    """Create an issuer client adapter that calls use cases directly."""
    return UseCaseIssuerClient(
        registration_service=registration_service,
        payment_channel_service=payment_channel_service,
        payword_channel_service=payword_channel_service,
        paytree_channel_service=paytree_channel_service,
        paytree_first_opt_channel_service=paytree_first_opt_channel_service,
        paytree_second_opt_channel_service=paytree_second_opt_channel_service,
    )


@pytest.fixture
def issuer_client_factory(
    registration_service: RegistrationService,
    payment_channel_service: PaymentChannelService,
    payword_channel_service: PaywordChannelService,
    paytree_channel_service: PaytreeChannelService,
    paytree_first_opt_channel_service: PaytreeFirstOptChannelService,
    paytree_second_opt_channel_service: PaytreeSecondOptChannelService,
) -> IssuerClientFactory:
    """Create an issuer client factory that returns the use case adapter."""

    def factory() -> IssuerClientProtocol:
        # Create a new instance each time (for context manager support)
        # UseCaseIssuerClient implements IssuerClientProtocol
        client: IssuerClientProtocol = UseCaseIssuerClient(
            registration_service=registration_service,
            payment_channel_service=payment_channel_service,
            payword_channel_service=payword_channel_service,
            paytree_channel_service=paytree_channel_service,
            paytree_first_opt_channel_service=paytree_first_opt_channel_service,
            paytree_second_opt_channel_service=paytree_second_opt_channel_service,
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
    """Get vendor private key as PEM string."""
    private_key, _ = vendor_key_pair
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def payment_service(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaymentService:
    """Create a payment service for testing."""
    return PaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def payword_payment_service(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaywordPaymentService:
    """Create a PayWord payment service for testing."""
    return PaywordPaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def paytree_payment_service(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreePaymentService:
    """Create a PayTree payment service for testing."""
    return PaytreePaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def paytree_first_opt_payment_service(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeFirstOptPaymentService:
    """Create a PayTree First Opt payment service for testing."""
    return PaytreeFirstOptPaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


@pytest.fixture
def paytree_second_opt_payment_service(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
    vendor_private_key_pem: str,
) -> PaytreeSecondOptPaymentService:
    """Create a PayTree Second Opt payment service for testing."""
    return PaytreeSecondOptPaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=vendor_private_key_pem,
    )


# ============================================================================
# Vendor Client Adapter Fixtures
# ============================================================================


@pytest.fixture
def vendor_client(
    payment_service: PaymentService,
    payword_payment_service: PaywordPaymentService,
    paytree_payment_service: PaytreePaymentService,
    paytree_first_opt_payment_service: PaytreeFirstOptPaymentService,
    paytree_second_opt_payment_service: PaytreeSecondOptPaymentService,
    vendor_public_key_der_b64: str,
) -> UseCaseVendorClient:
    """Create a vendor client adapter that calls use cases directly."""
    return UseCaseVendorClient(
        payment_service=payment_service,
        payword_payment_service=payword_payment_service,
        paytree_payment_service=paytree_payment_service,
        paytree_first_opt_payment_service=paytree_first_opt_payment_service,
        paytree_second_opt_payment_service=paytree_second_opt_payment_service,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )
