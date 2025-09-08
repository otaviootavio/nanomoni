"""Dependencies for Issuer API."""

from __future__ import annotations

from functools import lru_cache

from ...envs.issuer_env import get_settings, Settings
from ...infrastructure.database import get_database_client, DatabaseClient
from ...infrastructure.issuer.repositories import (
    SQLiteIssuerClientRepository,
    SQLiteIssuerChallengeRepository,
)
from ...application.issuer_use_case import IssuerService


@lru_cache()
def get_settings_dependency() -> Settings:
    return get_settings()


@lru_cache()
def get_database_client_dependency() -> DatabaseClient:
    settings = get_settings_dependency()
    return get_database_client(settings)


def get_issuer_client_repository() -> SQLiteIssuerClientRepository:
    db_client = get_database_client_dependency()
    return SQLiteIssuerClientRepository(db_client)


def get_issuer_challenge_repository() -> SQLiteIssuerChallengeRepository:
    db_client = get_database_client_dependency()
    return SQLiteIssuerChallengeRepository(db_client)


def get_issuer_service() -> IssuerService:
    client_repo = get_issuer_client_repository()
    challenge_repo = get_issuer_challenge_repository()
    settings = get_settings_dependency()
    return IssuerService(
        client_repo,
        challenge_repo,
        settings.issuer_private_key_pem,
    )
