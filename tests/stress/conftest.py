"""Shared fixtures for stress tests requiring external services."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


def check_service_health(url: str, timeout: float = 5.0) -> None:
    """
    Check if a service health endpoint is available and returns 200.

    Raises RuntimeError if the service is not available.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Service at {url} returned status {response.status_code}, expected 200"
                )
    except httpx.RequestError as e:
        raise RuntimeError(f"Failed to connect to service at {url}: {e}") from e


def check_redis_connection(url: str, timeout: float = 5.0) -> None:
    """
    Check if a Redis instance is reachable by pinging it.

    Raises RuntimeError if Redis is not available.
    """
    import redis as redis_sync

    try:
        # Use synchronous Redis client for health check in synchronous fixture
        redis_client = redis_sync.from_url(
            url, decode_responses=False, socket_connect_timeout=timeout
        )
        redis_client.ping()
        redis_client.close()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Redis at {url}: {e}") from e


def health_url(base_url: str) -> str:
    """
    Build a root health endpoint URL from a base URL.

    Stress/E2E tests often use base URLs like http://localhost:8001/api/v1, while the
    services expose health at /health (root). This helper makes health checks robust.
    """
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


@pytest.fixture(scope="session")
def require_services(
    issuer_base_url: str,
    vendor_base_url: str,
) -> None:
    """
    Session-scoped fixture that validates required external services are available.

    This fixture checks:
    - Issuer API health endpoint (GET /health)
    - Vendor API health endpoint (GET /health)
    - Redis vendor at localhost:6379
    - Redis issuer at localhost:6380

    Raises RuntimeError with clear instructions if any service is not available.
    Tests will not proceed unless all services are running.
    """
    errors = []

    # Check Issuer health
    issuer_health_url = health_url(issuer_base_url)
    try:
        check_service_health(issuer_health_url)
        print("[Stress] Issuer health check passed")
    except RuntimeError as e:
        errors.append(f"Issuer health check failed: {e}")

    # Check Vendor health
    vendor_health_url = health_url(vendor_base_url)
    try:
        check_service_health(vendor_health_url)
        print("[Stress] Vendor health check passed")
    except RuntimeError as e:
        errors.append(f"Vendor health check failed: {e}")

    # Check Redis vendor
    redis_vendor_url = "redis://localhost:6379/0"
    try:
        check_redis_connection(redis_vendor_url)
        print("[Stress] Redis vendor connection check passed")
    except RuntimeError as e:
        errors.append(f"Redis vendor (localhost:6379) check failed: {e}")

    # Check Redis issuer
    redis_issuer_url = "redis://localhost:6380/0"
    try:
        check_redis_connection(redis_issuer_url)
        print("[Stress] Redis issuer connection check passed")
    except RuntimeError as e:
        errors.append(f"Redis issuer (localhost:6380) check failed: {e}")

    # If any checks failed, raise with clear error message
    if errors:
        error_msg = (
            "\n[Stress] Required services are not available:\n"
            + "\n".join(f"  - {err}" for err in errors)
            + "\n\n"
            + "Please start the required services with:\n"
            + "  docker compose up -d issuer vendor redis-issuer redis-vendor\n\n"
            + "Then wait for services to be ready and run the tests again."
        )
        raise RuntimeError(error_msg)

    print("[Stress] All required services are available")


@pytest.fixture
def issuer_client(issuer_base_url: str, require_services: None) -> IssuerTestClient:
    """Provide an IssuerTestClient instance for stress tests."""
    return IssuerTestClient(base_url=issuer_base_url)


@pytest.fixture
def vendor_client(vendor_base_url: str, require_services: None) -> VendorTestClient:
    """Provide a VendorTestClient instance for stress tests."""
    return VendorTestClient(base_url=vendor_base_url)
