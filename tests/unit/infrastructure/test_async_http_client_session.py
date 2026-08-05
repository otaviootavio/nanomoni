"""AsyncHttpClient shared-session ownership (Fix B / P2)."""

from __future__ import annotations

import aiohttp
import pytest

from nanomoni.infrastructure.http.http_client import (
    AsyncHttpClient,
    DEDICATED_CONNECTION_KEEPALIVE_S,
)


@pytest.mark.asyncio
async def test_shared_session_is_not_closed_on_aclose() -> None:
    shared = aiohttp.ClientSession()
    try:
        client = AsyncHttpClient("http://example.test", session=shared)
        assert client._owns_session is False
        await client.aclose()
        assert not shared.closed
    finally:
        await shared.close()


@pytest.mark.asyncio
async def test_owned_session_is_closed_on_aclose() -> None:
    client = AsyncHttpClient("http://example.test")
    assert client._owns_session is True
    owned = client._client
    await client.aclose()
    assert owned.closed


@pytest.mark.asyncio
async def test_connection_limit_caps_the_owned_pool() -> None:
    """A limit of 1 is what keeps a virtual client on a single Uvicorn worker."""
    client = AsyncHttpClient("http://example.test", connection_limit=1)
    try:
        connector = client._client.connector
        assert connector is not None
        assert connector.limit == 1
        # Shorter than the vendor's keep-alive would silently drop the connection
        # during an idle gap and let another worker accept the replacement.
        assert connector._keepalive_timeout == DEDICATED_CONNECTION_KEEPALIVE_S
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_pool_is_unbounded_without_a_connection_limit() -> None:
    client = AsyncHttpClient("http://example.test")
    try:
        connector = client._client.connector
        assert connector is not None
        assert connector.limit != 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_borrowed_session_ignores_connection_limit() -> None:
    shared = aiohttp.ClientSession()
    try:
        client = AsyncHttpClient(
            "http://example.test", session=shared, connection_limit=1
        )
        assert client._client is shared
    finally:
        await shared.close()


@pytest.mark.asyncio
async def test_async_with_does_not_close_shared_session() -> None:
    shared = aiohttp.ClientSession()
    try:
        async with AsyncHttpClient("http://example.test", session=shared):
            pass
        assert not shared.closed
    finally:
        await shared.close()
