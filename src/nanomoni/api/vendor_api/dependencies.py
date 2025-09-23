"""Dependency injection for Vendor FastAPI."""

from __future__ import annotations

from functools import lru_cache

from ...envs.vendor_env import get_settings, Settings
from ...infrastructure.database import get_database_client, DatabaseClient
from ...infrastructure.storage import RedisKeyValueStore
from ...infrastructure.vendor.user_repository_impl import UserRepositoryImpl
from ...infrastructure.vendor.task_repository_impl import TaskRepositoryImpl
from ...infrastructure.vendor.off_chain_tx_repository_impl import (
    OffChainTxRepositoryImpl,
)
from ...application.vendor_use_case import UserService, TaskService, PaymentService


@lru_cache()
def get_settings_dependency() -> Settings:
    return get_settings()


@lru_cache()
def get_database_client_dependency() -> DatabaseClient:
    settings = get_settings_dependency()
    return get_database_client(settings)


@lru_cache()
def get_store_dependency() -> RedisKeyValueStore:
    db_client = get_database_client_dependency()
    return RedisKeyValueStore(db_client)


def get_user_repository() -> UserRepositoryImpl:
    store = get_store_dependency()
    return UserRepositoryImpl(store)


def get_task_repository() -> TaskRepositoryImpl:
    store = get_store_dependency()
    return TaskRepositoryImpl(store)


def get_off_chain_tx_repository() -> OffChainTxRepositoryImpl:
    store = get_store_dependency()
    return OffChainTxRepositoryImpl(store)


def get_user_service() -> UserService:
    user_repository = get_user_repository()
    return UserService(user_repository)


def get_task_service() -> TaskService:
    task_repository = get_task_repository()
    user_repository = get_user_repository()
    return TaskService(task_repository, user_repository)


def get_payment_service() -> PaymentService:
    off_chain_tx_repository = get_off_chain_tx_repository()
    settings = get_settings_dependency()
    return PaymentService(off_chain_tx_repository, settings.issuer_base_url)
