"""Shared pytest fixtures for E2E tests using docker compose."""

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

    - Runs `docker compose down -v` to clean up any existing stack
    - Starts required services: issuer, vendor, redis-issuer, redis-vendor
    - Polls health endpoints until services are ready
    - Tears down with `docker compose down -v` after all tests complete
    """
    project_root = Path(__file__).parent.parent.parent

    # Clean up any existing stack
    print("\n[E2E] Cleaning up existing docker compose stack...")
    run_compose_command(["down", "-v"], cwd=project_root)

    # Start required services
    print(
        "[E2E] Starting docker compose services (issuer, vendor, redis-issuer, redis-vendor)..."
    )
    result = run_compose_command(
        ["up", "-d", "issuer", "vendor", "redis-issuer", "redis-vendor"],
        cwd=project_root,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start docker compose services:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    # Wait for services to become healthy
    print("[E2E] Waiting for services to become healthy...")
    try:
        wait_for_service("http://localhost:8001/health", timeout=60.0)  # Issuer
        print("[E2E] Issuer is healthy")

        wait_for_service("http://localhost:8000/health", timeout=60.0)  # Vendor
        print("[E2E] Vendor is healthy")

        print("[E2E] All services are ready")
    except TimeoutError:
        # Try to get logs for debugging
        print("\n[E2E] Service health check failed. Container logs:")
        run_compose_command(["logs", "--tail=50"], cwd=project_root)
        raise

    yield

    # Teardown: stop and remove containers, networks, and volumes
    print("\n[E2E] Tearing down docker compose stack...")
    run_compose_command(["down", "-v"], cwd=project_root)
    print("[E2E] Teardown complete")


@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_redis_between_tests(
    docker_compose_stack: None,  # Ensure stack is running
) -> AsyncGenerator[None, None]:
    """
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
    except Exception as e:
        # Silently ignore if Redis is not available (e.g., during setup/teardown)
        pass

    # Flush issuer Redis
    try:
        issuer_client = redis.from_url(redis_issuer_url, decode_responses=False)
        await issuer_client.flushdb()
        await issuer_client.aclose()
    except Exception as e:
        # Silently ignore if Redis is not available (e.g., during setup/teardown)
        pass
