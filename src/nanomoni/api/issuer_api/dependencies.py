"""Dependencies for Issuer API."""

from __future__ import annotations

from functools import lru_cache

from ...envs.issuer_env import get_settings, Settings
from ...infrastructure.database import get_database_client, DatabaseClient
from ...infrastructure.storage import RedisKeyValueStore
from ...infrastructure.issuer.account_repository_impl import AccountRepositoryImpl
from ...infrastructure.issuer.payment_channel_repository_impl import (
    PaymentChannelRepositoryImpl,
)
from ...application.issuer.use_cases.registration import RegistrationService
from ...application.issuer.use_cases.payment_channel import PaymentChannelService
from ...application.issuer.use_cases.payword_channel import PaywordChannelService
from ...application.issuer.use_cases.paytree_channel import PaytreeChannelService
from ...application.issuer.use_cases.paytree_first_opt_channel import (
    PaytreeFirstOptChannelService,
)
from ...application.issuer.use_cases.paytree_second_opt_channel import (
    PaytreeSecondOptChannelService,
)


@lru_cache
def get_settings_dependency() -> Settings:
    return get_settings()


@lru_cache
def get_database_client_dependency() -> DatabaseClient:
    settings = get_settings_dependency()
    return get_database_client(settings)


@lru_cache
def get_store_dependency() -> RedisKeyValueStore:
    db_client = get_database_client_dependency()
    return RedisKeyValueStore(db_client)


def get_account_repository() -> AccountRepositoryImpl:
    store = get_store_dependency()
    return AccountRepositoryImpl(store)


def get_payment_channel_repository() -> PaymentChannelRepositoryImpl:
    store = get_store_dependency()
    return PaymentChannelRepositoryImpl(store)


def get_issuer_service() -> RegistrationService:
    account_repo = get_account_repository()
    settings = get_settings_dependency()
    return RegistrationService(
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


def get_payword_channel_service() -> PaywordChannelService:
    account_repo = get_account_repository()
    channel_repo = get_payment_channel_repository()
    settings = get_settings_dependency()
    return PaywordChannelService(
        account_repo, channel_repo, settings.issuer_private_key
    )


def get_paytree_channel_service() -> PaytreeChannelService:
    account_repo = get_account_repository()
    channel_repo = get_payment_channel_repository()
    settings = get_settings_dependency()
    return PaytreeChannelService(
        account_repo, channel_repo, settings.issuer_private_key
    )


def get_paytree_first_opt_channel_service() -> PaytreeFirstOptChannelService:
    account_repo = get_account_repository()
    channel_repo = get_payment_channel_repository()
    settings = get_settings_dependency()
    return PaytreeFirstOptChannelService(
        account_repo, channel_repo, settings.issuer_private_key
    )


def get_paytree_second_opt_channel_service() -> PaytreeSecondOptChannelService:
    account_repo = get_account_repository()
    channel_repo = get_payment_channel_repository()
    settings = get_settings_dependency()
    return PaytreeSecondOptChannelService(
        account_repo, channel_repo, settings.issuer_private_key
    )
