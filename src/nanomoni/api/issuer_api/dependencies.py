"""Dependencies for Issuer API."""

from __future__ import annotations

from functools import lru_cache

from ...envs.issuer_env import get_settings, Settings
from ...infrastructure.database import get_database_client, DatabaseClient
from ...infrastructure.storage import RedisKeyValueStore
from ...infrastructure.issuer.repositories import (
    AccountRepositoryImpl,
    PaymentChannelRepositoryImpl,
)
from ...application.issuer_use_case import IssuerService
from ...application.issuer.use_cases.payment_channel import PaymentChannelService


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


def get_account_repository() -> AccountRepositoryImpl:
    store = get_store_dependency()
    return AccountRepositoryImpl(store)


def get_payment_channel_repository() -> PaymentChannelRepositoryImpl:
    store = get_store_dependency()
    return PaymentChannelRepositoryImpl(store)


def get_issuer_service() -> IssuerService:
    account_repo = get_account_repository()
    settings = get_settings_dependency()
    return IssuerService(
        settings.issuer_private_key_pem,
        account_repo,
    )


def get_payment_channel_service() -> PaymentChannelService:
    account_repo = get_account_repository()
    channel_repo = get_payment_channel_repository()
    settings = get_settings_dependency()
    return PaymentChannelService(
        account_repo, channel_repo, settings.issuer_private_key
    )
