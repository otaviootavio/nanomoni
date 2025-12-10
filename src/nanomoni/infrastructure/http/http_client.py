from __future__ import annotations

from typing import Any, Dict, Optional, Type
from types import TracebackType

import httpx


class HttpClient:
    """Thin synchronous HTTP client wrapper around httpx.

    - Normalizes base URLs and paths.
    - Applies a default timeout.
    - Raises for non-successful responses.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.get(self._url(path), **kwargs)
        resp.raise_for_status()
        return resp

    def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        resp = self._client.post(self._url(path), json=json, **kwargs)
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()


class AsyncHttpClient:
    """Thin asynchronous HTTP client wrapper around httpx.AsyncClient.

    - Normalizes base URLs and paths.
    - Applies a default timeout.
    - Raises for non-successful responses.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.get(self._url(path), **kwargs)
        resp.raise_for_status()
        return resp

    async def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        resp = await self._client.post(self._url(path), json=json, **kwargs)
        resp.raise_for_status()
        return resp

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.aclose()
