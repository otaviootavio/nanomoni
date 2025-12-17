"""FastAPI dependencies for the vendor API."""

from __future__ import annotations

from fastapi import Depends

from ...application.vendor.use_cases.payment import PaymentService
from ...application.vendor.use_cases.task import TaskService
from ...application.vendor.use_cases.user import UserService
from ...domain.vendor.payment_channel_repository import PaymentChannelRepository
from ...domain.vendor.task_repository import TaskRepository
from ...domain.vendor.user_repository import UserRepository
from ...infrastructure.database import DatabaseClient, get_database_client
from ...infrastructure.storage import KeyValueStore, RedisKeyValueStore
from ...infrastructure.vendor.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)
from ...infrastructure.vendor.task_repository_impl import TaskRepositoryImpl
from ...infrastructure.vendor.user_repository_impl import UserRepositoryImpl
from ...envs.vendor_env import Settings, get_settings


def get_database_client_with_settings(
    settings: Settings = Depends(get_settings),
) -> DatabaseClient:
    """Get database client with settings."""
    return get_database_client(settings)


def get_key_value_store(
    db_client: DatabaseClient = Depends(get_database_client_with_settings),
) -> KeyValueStore:
    """Get key-value store."""
    return RedisKeyValueStore(db_client)


def get_user_repository(
    store: KeyValueStore = Depends(get_key_value_store),
) -> UserRepository:
    """Get user repository."""
    return UserRepositoryImpl(store)


def get_task_repository(
    store: KeyValueStore = Depends(get_key_value_store),
) -> TaskRepository:
    """Get task repository."""
    return TaskRepositoryImpl(store)


def get_payment_channel_repository(
    store: KeyValueStore = Depends(get_key_value_store),
) -> PaymentChannelRepository:
    """Get payment channel repository."""
    return PaymentChannelRepositoryImpl(store)


def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    """Get user service."""
    return UserService(user_repository)


def get_task_service(
    task_repository: TaskRepository = Depends(get_task_repository),
    user_repository: UserRepository = Depends(get_user_repository),
) -> TaskService:
    """Get task service."""
    return TaskService(task_repository, user_repository)


def get_payment_service(
    payment_channel_repository: PaymentChannelRepository = Depends(
        get_payment_channel_repository
    ),
    settings: Settings = Depends(get_settings),
) -> PaymentService:
    """Get payment service."""
    return PaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_base_url=settings.issuer_base_url,
        vendor_public_key_der_b64=settings.vendor_public_key_der_b64,
        vendor_private_key_pem=settings.vendor_private_key_pem,
    )
