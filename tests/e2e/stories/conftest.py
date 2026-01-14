"""Shared fixtures for story tests."""

from __future__ import annotations

from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


def _httpx_limits() -> httpx.Limits:
    return httpx.Limits(max_connections=50, max_keepalive_connections=10)


def _httpx_timeout() -> httpx.Timeout:
    return httpx.Timeout(30.0)


@pytest_asyncio.fixture
async def issuer_httpx_client(
    require_services: None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        timeout=_httpx_timeout(),
        limits=_httpx_limits(),
        headers={"Connection": "keep-alive"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def vendor_httpx_client(
    require_services: None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        timeout=_httpx_timeout(),
        limits=_httpx_limits(),
        headers={"Connection": "keep-alive"},
    ) as client:
        yield client


@pytest.fixture
def issuer_client(
    issuer_base_url: str,
    issuer_httpx_client: httpx.AsyncClient,
    require_services: None,
) -> IssuerTestClient:
    """Provide a session-scoped IssuerTestClient with a shared HTTP pool."""
    return IssuerTestClient(base_url=issuer_base_url, http_client=issuer_httpx_client)


@pytest.fixture
def vendor_client(
    vendor_base_url: str,
    vendor_httpx_client: httpx.AsyncClient,
    require_services: None,
) -> VendorTestClient:
    """Provide a session-scoped VendorTestClient with a shared HTTP pool."""
    return VendorTestClient(base_url=vendor_base_url, http_client=vendor_httpx_client)
