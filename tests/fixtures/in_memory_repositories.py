"""In-memory repository implementations for testing."""

from __future__ import annotations

from dataclasses import dataclass

from nanomoni.domain.vendor.payment_channel_repository import (
    PaymentRepository,
    SignatureRepository,
)
from nanomoni.infrastructure.scripts import VENDOR_SCRIPTS, ISSUER_SCRIPTS
from nanomoni.infrastructure.vendor.payment_repository_impl import PaymentRepositoryImpl
from nanomoni.infrastructure.vendor.signature_repository_impl import (
    SignatureRepositoryImpl,
)
from nanomoni.infrastructure.vendor.user_repository_impl import UserRepositoryImpl
from nanomoni.infrastructure.vendor.task_repository_impl import TaskRepositoryImpl
from nanomoni.infrastructure.issuer.account_repository_impl import (
    AccountRepositoryImpl,
)
from nanomoni.infrastructure.issuer.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl as IssuerPaymentChannelRepositoryImpl,
)

from .in_memory_storage import InMemoryKeyValueStore


async def _register_vendor_scripts(store: InMemoryKeyValueStore) -> None:
    """Register vendor Lua scripts in the in-memory store."""
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)


async def _register_issuer_scripts(store: InMemoryKeyValueStore) -> None:
    """Register issuer Lua scripts in the in-memory store."""
    for name, script in ISSUER_SCRIPTS.items():
        await store.register_script(name, script)


@dataclass
class VendorPaymentRepositories:
    """Container of vendor payment repositories sharing one store."""

    signature: SignatureRepository
    payment: PaymentRepository
    store: InMemoryKeyValueStore

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self.store.clear()


def create_vendor_payment_repositories() -> VendorPaymentRepositories:
    """Create in-memory vendor payment repositories sharing one store."""
    store = InMemoryKeyValueStore()
    return VendorPaymentRepositories(
        signature=SignatureRepositoryImpl(store),
        payment=PaymentRepositoryImpl(store),
        store=store,
    )


async def initialize_vendor_payment_repositories(
    repos: VendorPaymentRepositories,
) -> None:
    """Register vendor Lua scripts in the shared store."""
    await _register_vendor_scripts(repos.store)


class InMemoryAccountRepository(AccountRepositoryImpl):
    """In-memory account repository for issuer testing."""

    def __init__(self) -> None:
        store = InMemoryKeyValueStore()
        super().__init__(store)
        self._store = store

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self._store.clear()


class InMemoryIssuerPaymentChannelRepository(IssuerPaymentChannelRepositoryImpl):
    """In-memory payment channel repository for issuer testing."""

    def __init__(self) -> None:
        store = InMemoryKeyValueStore()
        super().__init__(store)
        self._store = store
        # Scripts will be registered when needed (async)

    async def initialize(self) -> None:
        """Initialize the repository by registering scripts."""
        await _register_issuer_scripts(self._store)

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self._store.clear()


class InMemoryUserRepository(UserRepositoryImpl):
    """In-memory user repository for testing."""

    def __init__(self) -> None:
        store = InMemoryKeyValueStore()
        super().__init__(store)
        self._store = store

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self._store.clear()


class InMemoryTaskRepository(TaskRepositoryImpl):
    """In-memory task repository for testing."""

    def __init__(self) -> None:
        store = InMemoryKeyValueStore()
        super().__init__(store)
        self._store = store

    def clear(self) -> None:
        """Clear all data (useful for test teardown)."""
        self._store.clear()
