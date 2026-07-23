"""AsyncHttpClient shared-session ownership (Fix B / P2)."""

from __future__ import annotations

import aiohttp
import pytest

from nanomoni.infrastructure.http.http_client import AsyncHttpClient


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
async def test_async_with_does_not_close_shared_session() -> None:
    shared = aiohttp.ClientSession()
    try:
        async with AsyncHttpClient("http://example.test", session=shared):
            pass
        assert not shared.closed
    finally:
        await shared.close()
