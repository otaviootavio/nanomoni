"""Shared fixtures for stress tests."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


def run_compose_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a docker compose command and return the result."""
    cmd = ["docker", "compose"] + args
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def wait_for_service(url: str, timeout: float = 60.0, interval: float = 1.0) -> None:
    """Wait for a service to become healthy by polling a health endpoint."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        time.sleep(interval)
    raise TimeoutError(f"Service at {url} did not become healthy within {timeout}s")


@pytest.fixture(scope="session")
def docker_compose_stack() -> Generator[None, None, None]:
    """
    Session-scoped fixture that manages the docker compose stack lifecycle.

    - Stops and removes only the test services if they're already running
    - Starts required services: issuer, vendor, redis-issuer, redis-vendor
    - Polls health endpoints until services are ready
    - Tears down only the test services after all tests complete
    """
    project_root = Path(__file__).parent.parent.parent

    # Services that this test manages
    test_services = ["issuer", "vendor", "redis-issuer", "redis-vendor"]

    # Clean up any existing test services (stop and remove containers)
    print("\n[Stress] Cleaning up existing test services...")
    # Stop the specific services we manage
    run_compose_command(["stop"] + test_services, cwd=project_root)
    # Remove containers for those services
    run_compose_command(["rm", "-f"] + test_services, cwd=project_root)

    # Start required services
    print(f"[Stress] Starting docker compose services ({', '.join(test_services)})...")
    result = run_compose_command(
        ["up", "-d"] + test_services,
        cwd=project_root,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start docker compose services:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    # Wait for services to become healthy
    print("[Stress] Waiting for services to become healthy...")
    try:
        wait_for_service("http://localhost:8001/health", timeout=60.0)  # Issuer
        print("[Stress] Issuer is healthy")

        wait_for_service("http://localhost:8000/health", timeout=60.0)  # Vendor
        print("[Stress] Vendor is healthy")

        print("[Stress] All services are ready")
    except TimeoutError:
        # Try to get logs for debugging
        print("\n[Stress] Service health check failed. Container logs:")
        run_compose_command(["logs", "--tail=50"] + test_services, cwd=project_root)
        raise

    yield

    # Teardown: stop and remove only the test services (not all services)
    print("\n[Stress] Tearing down test services...")
    run_compose_command(["stop"] + test_services, cwd=project_root)
    run_compose_command(["rm", "-f"] + test_services, cwd=project_root)
    print("[Stress] Teardown complete")


@pytest.fixture
def issuer_client() -> IssuerTestClient:
    """Provide an IssuerTestClient instance for stress tests."""
    return IssuerTestClient()


@pytest.fixture
def vendor_client() -> VendorTestClient:
    """Provide a VendorTestClient instance for stress tests."""
    return VendorTestClient()


@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_redis(
    docker_compose_stack: None,  # Ensure stack is running - override base conftest
) -> AsyncGenerator[None, None]:
    """
    Override base conftest's cleanup_redis to use docker compose instead.

    This ensures docker_compose_stack runs first, making Redis available.
    Automatically flush Redis databases between each test for isolation.

    This fixture runs before and after each test to ensure:
    - Each test starts with a clean Redis state
    - Test data doesn't leak between tests
    - Tests are independent and can run in any order

    Flushes both:
    - redis-vendor (localhost:6379, database 0)
    - redis-issuer (localhost:6380, database 0)
    """
    # Pre-test: Ensure clean state (flush before test runs)
    await _flush_redis_instances()

    yield

    # Post-test: Clean up after test completes
    await _flush_redis_instances()


async def _flush_redis_instances() -> None:
    """Flush both Redis instances (vendor and issuer) to ensure test isolation."""
    redis_vendor_url = "redis://localhost:6379/0"
    redis_issuer_url = "redis://localhost:6380/0"

    # Flush vendor Redis
    try:
        vendor_client = redis.from_url(redis_vendor_url, decode_responses=False)
        await vendor_client.flushdb()
        await vendor_client.aclose()
    except Exception:
        # Silently ignore if Redis is not available (e.g., during setup/teardown)
        pass

    # Flush issuer Redis
    try:
        issuer_client = redis.from_url(redis_issuer_url, decode_responses=False)
        await issuer_client.flushdb()
        await issuer_client.aclose()
    except Exception:
        # Silently ignore if Redis is not available (e.g., during setup/teardown)
        pass
