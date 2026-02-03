"""FastAPI dependencies for the vendor API."""

from __future__ import annotations

from functools import lru_cache

from ...application.vendor.use_cases.payment import PaymentService
from ...application.vendor.use_cases.payword_payment import PaywordPaymentService
from ...application.vendor.use_cases.paytree_payment import PaytreePaymentService
from ...application.vendor.use_cases.task import TaskService
from ...application.vendor.use_cases.user import UserService
from ...domain.shared import IssuerClientFactory
from ...domain.vendor.payment_channel_repository import PaymentChannelRepository
from ...domain.vendor.task_repository import TaskRepository
from ...domain.vendor.user_repository import UserRepository
from ...infrastructure.database import DatabaseClient, get_database_client
from ...infrastructure.issuer.issuer_client import AsyncIssuerClient
from ...infrastructure.storage import KeyValueStore, RedisKeyValueStore
from ...infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)
from ...infrastructure.vendor.task_repository_impl import TaskRepositoryImpl
from ...infrastructure.vendor.user_repository_impl import UserRepositoryImpl
from ...envs.vendor_env import Settings, get_settings as _get_settings


@lru_cache
def get_settings_dependency() -> Settings:
    """Process-wide cached settings (safe because env vars are static at runtime)."""
    return _get_settings()


@lru_cache
def get_database_client_dependency() -> DatabaseClient:
    """Process-wide cached DB client."""
    settings = get_settings_dependency()
    return get_database_client(settings)


@lru_cache
def get_key_value_store_dependency() -> KeyValueStore:
    """Process-wide cached store."""
    return RedisKeyValueStore(get_database_client_dependency())


def get_user_repository() -> UserRepository:
    """Get user repository."""
    return UserRepositoryImpl(get_key_value_store_dependency())


def get_task_repository() -> TaskRepository:
    """Get task repository."""
    return TaskRepositoryImpl(get_key_value_store_dependency())


def get_payment_channel_repository() -> PaymentChannelRepository:
    """Get payment channel repository."""
    return PaymentChannelRepositoryImpl(get_key_value_store_dependency())


def get_user_service() -> UserService:
    """Get user service."""
    return UserService(get_user_repository())


def get_task_service() -> TaskService:
    """Get task service."""
    return TaskService(get_task_repository(), get_user_repository())


def _create_issuer_client_factory(
    issuer_base_url: str,
) -> IssuerClientFactory:
    """Create a factory function that returns AsyncIssuerClient instances."""

    def factory() -> AsyncIssuerClient:
        return AsyncIssuerClient(issuer_base_url)

    return factory


def get_payment_service() -> PaymentService:
    """Get payment service."""
    payment_channel_repository = get_payment_channel_repository()
    settings = get_settings_dependency()
    issuer_client_factory = _create_issuer_client_factory(settings.issuer_base_url)
    return PaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=settings.vendor_public_key_der_b64,
        vendor_private_key_pem=settings.vendor_private_key_pem,
    )


def get_payword_payment_service() -> PaywordPaymentService:
    """Get PayWord payment service."""
    payment_channel_repository = get_payment_channel_repository()
    settings = get_settings_dependency()
    issuer_client_factory = _create_issuer_client_factory(settings.issuer_base_url)
    return PaywordPaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=settings.vendor_public_key_der_b64,
        vendor_private_key_pem=settings.vendor_private_key_pem,
    )


def get_paytree_payment_service() -> PaytreePaymentService:
    """Get PayTree payment service."""
    payment_channel_repository = get_payment_channel_repository()
    settings = get_settings_dependency()
    issuer_client_factory = _create_issuer_client_factory(settings.issuer_base_url)
    return PaytreePaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=settings.vendor_public_key_der_b64,
        vendor_private_key_pem=settings.vendor_private_key_pem,
    )
