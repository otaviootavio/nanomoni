from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type
from types import TracebackType
from urllib.request import Request, urlopen

import aiohttp


class HttpError(Exception):
    """Base error for HTTP client operations."""


@dataclass(frozen=True)
class HttpResponse:
    """Minimal response object with a stable API used across the codebase."""

    status_code: int
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.content:
            return None
        return json.loads(self.text)


class HttpRequestError(HttpError):
    """Raised for network/transport errors (no HTTP response)."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class HttpResponseError(HttpError):
    """Raised for non-2xx HTTP responses."""

    def __init__(self, response: HttpResponse, message: str | None = None) -> None:
        self.response = response
        super().__init__(message or f"HTTP {response.status_code}")


class HttpClient:
    """Thin synchronous HTTP client wrapper.

    - Normalizes base URLs and paths.
    - Applies a default timeout.
    - Raises for non-successful responses.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **_kwargs: Any,
    ) -> HttpResponse:
        url = self._url(path)
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if json is not None:
            data = json_module_dumps(json).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url=url, method=method, data=data, headers=headers)
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", 200)
                content = resp.read()
        except Exception as e:
            raise HttpRequestError(f"Request failed: {method} {url}", cause=e) from e

        response = HttpResponse(status_code=status, content=content)
        if response.status_code >= 400:
            raise HttpResponseError(response)
        return response

    def get(self, path: str, **kwargs: Any) -> HttpResponse:
        return self._request("GET", path, **kwargs)

    def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return self._request("POST", path, json=json, **kwargs)

    def close(self) -> None:
        # No persistent resources for the stdlib implementation.
        return None

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
    """Thin asynchronous HTTP client wrapper around aiohttp.ClientSession.

    - Normalizes base URLs and paths.
    - Applies a default timeout.
    - Raises for non-successful responses.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._client = aiohttp.ClientSession(timeout=self._timeout)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    async def get(self, path: str, **kwargs: Any) -> HttpResponse:
        return await self._request("GET", path, **kwargs)

    async def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return await self._request("POST", path, json=json, **kwargs)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> HttpResponse:
        url = self._url(path)
        try:
            async with self._client.request(method, url, json=json, **kwargs) as resp:
                content = await resp.read()
                response = HttpResponse(status_code=resp.status, content=content)
        except aiohttp.ClientError as e:
            raise HttpRequestError(f"Request failed: {method} {url}", cause=e) from e

        if response.status_code >= 400:
            raise HttpResponseError(response)
        return response

    async def aclose(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.aclose()


def json_module_dumps(obj: Any) -> str:
    # Centralized JSON encoding for both sync and async clients.
    # Keep standard behavior (utf-8, no custom encoders).
    return json.dumps(obj)
