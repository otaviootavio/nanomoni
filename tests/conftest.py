"""Shared pytest fixtures for vendor payment tests."""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.infrastructure.database import DatabaseClient
from nanomoni.infrastructure.storage import RedisKeyValueStore


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command-line options for race condition tests."""
    parser.addoption(
        "--race-iterations",
        type=int,
        default=1000,
        help="Number of iterations to run for race condition tests (default: 1000)",
    )
    parser.addoption(
        "--min-lost-updates",
        type=int,
        default=0,
        help="Minimum number of lost updates expected (default: 0, set to >0 to require lost updates)",
    )


@pytest.fixture
def client_key_pair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """Generate a client key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def vendor_key_pair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """Generate a vendor key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def client_public_key_der_b64(
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    """Get client public key as DER base64 string."""
    _, public_key = client_key_pair
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    import base64

    return base64.b64encode(der).decode("utf-8")


@pytest.fixture
def vendor_public_key_der_b64(
    vendor_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    """Get vendor public key as DER base64 string."""
    _, public_key = vendor_key_pair
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    import base64

    return base64.b64encode(der).decode("utf-8")


@pytest.fixture
def client_private_key_pem(
    client_key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> str:
    """Get client private key as PEM string."""
    private_key, _ = client_key_pair
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


class TestDatabaseSettings:
    """Test settings for Redis connection."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url


@pytest_asyncio.fixture
async def redis_db_client() -> AsyncGenerator[DatabaseClient, None]:
    """Create a Redis database client for testing.

    Uses database 15 by default, or TEST_REDIS_URL if set.
    Falls back to localhost:6379/15 if not specified.
    """
    import warnings

    test_redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
    settings = TestDatabaseSettings(database_url=test_redis_url)
    client = DatabaseClient(settings)
    client.initialize_database()

    # Test connection
    try:
        async with client.get_connection() as conn:
            await conn.ping()
    except Exception as e:
        warnings.warn(
            f"Redis not available at {test_redis_url}: {e}. "
            "Tests requiring Redis will be skipped. "
            "Start Redis with: docker compose up redis-vendor -d",
            UserWarning,
        )
        pytest.skip(f"Redis not available: {e}")

    yield client

    # Cleanup: flush test database
    try:
        async with client.get_connection() as conn:
            await conn.flushdb()
    except Exception:
        pass  # Ignore cleanup errors


@pytest_asyncio.fixture
async def redis_store(redis_db_client: DatabaseClient) -> RedisKeyValueStore:
    """Create a Redis-backed key-value store for testing."""
    return RedisKeyValueStore(redis_db_client)


@pytest.fixture(scope="session")
def issuer_base_url() -> str:
    """
    Base URL for the Issuer API used by E2E/stress tests.

    Centralized here so helper clients don't reach into environment variables directly.
    The base URL should include /api/v1 prefix.
    """
    base_url = os.getenv("ISSUER_BASE_URL", "http://localhost:8001/api/v1")
    return base_url.rstrip("/")


@pytest.fixture(scope="session")
def vendor_base_url() -> str:
    """
    Base URL for the Vendor API used by E2E/stress tests.

    Centralized here so helper clients don't reach into environment variables directly.
    The base URL should include /api/v1 prefix.
    """
    base_url = os.getenv("VENDOR_BASE_URL", "http://localhost:8000/api/v1")
    return base_url.rstrip("/")
