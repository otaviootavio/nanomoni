"""Shared fixtures for story tests."""

from __future__ import annotations

from typing import AsyncGenerator

import aiohttp
import pytest
import pytest_asyncio

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


def _aiohttp_connector() -> aiohttp.TCPConnector:
    # Rough equivalent to the prior connection limits used in these tests.
    return aiohttp.TCPConnector(limit=50, limit_per_host=0, enable_cleanup_closed=True)


def _aiohttp_timeout() -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=30.0)


@pytest_asyncio.fixture
async def issuer_http_client(
    require_services: None,
) -> AsyncGenerator[aiohttp.ClientSession, None]:
    connector = _aiohttp_connector()
    async with aiohttp.ClientSession(
        timeout=_aiohttp_timeout(),
        connector=connector,
        headers={"Connection": "keep-alive"},
    ) as session:
        yield session


@pytest_asyncio.fixture
async def vendor_http_client(
    require_services: None,
) -> AsyncGenerator[aiohttp.ClientSession, None]:
    connector = _aiohttp_connector()
    async with aiohttp.ClientSession(
        timeout=_aiohttp_timeout(),
        connector=connector,
        headers={"Connection": "keep-alive"},
    ) as session:
        yield session


@pytest.fixture
def issuer_client(
    issuer_base_url: str,
    issuer_http_client: aiohttp.ClientSession,
    require_services: None,
) -> IssuerTestClient:
    """Provide a session-scoped IssuerTestClient with a shared HTTP pool."""
    return IssuerTestClient(base_url=issuer_base_url, http_client=issuer_http_client)


@pytest.fixture
def vendor_client(
    vendor_base_url: str,
    vendor_http_client: aiohttp.ClientSession,
    require_services: None,
) -> VendorTestClient:
    """Provide a session-scoped VendorTestClient with a shared HTTP pool."""
    return VendorTestClient(base_url=vendor_base_url, http_client=vendor_http_client)
