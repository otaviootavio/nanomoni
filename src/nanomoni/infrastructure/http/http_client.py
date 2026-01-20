from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Type
from types import TracebackType
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.error import HTTPError
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
        # Expose the underlying exception in a stable attribute for callers that
        # want to classify transient errors (e.g., retries). Also set __cause__
        # so exception chaining works naturally (and for backwards compat with
        # code that inspects __cause__ directly).
        self.cause = cause
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
        # Allow absolute http(s) URLs, or resolve relative paths against base_url.
        # Explicitly reject other schemes (e.g., file://) and scheme-relative URLs (//host).
        parsed = urlsplit(path)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(
                    f"Unsupported URL scheme {parsed.scheme!r} for request path {path!r}; "
                    "only http:// and https:// are allowed"
                )
            return path
        if parsed.netloc:
            raise ValueError(
                f"Unsupported scheme-relative URL {path!r}; only http:// and https:// are allowed"
            )
        base = urlsplit(self._base_url)
        if base.scheme not in {"http", "https"}:
            raise ValueError(
                f"Unsupported base URL scheme {base.scheme!r} for base_url {self._base_url!r}; "
                "only http:// and https:// are allowed"
            )
        return urljoin(f"{self._base_url}/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        auth: tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        url = self._url(path)
        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise TypeError(
                f"Unsupported keyword arguments for HttpClient._request: {unexpected}. "
                "Supported: headers, params, timeout, auth, cookies."
            )

        if params:
            split = urlsplit(url)
            new_query = urlencode(params, doseq=True)
            if split.query and new_query:
                combined = f"{split.query}&{new_query}"
            else:
                combined = split.query or new_query
            url = split._replace(query=combined).geturl()

        req_headers: dict[str, str] = {"Accept": "application/json"}
        if headers:
            req_headers.update(dict(headers))

        if auth is not None and not any(
            k.lower() == "authorization" for k in req_headers
        ):
            user, password = auth
            token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode(
                "ascii"
            )
            req_headers["Authorization"] = f"Basic {token}"

        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            existing_cookie_key = next(
                (k for k in req_headers.keys() if k.lower() == "cookie"), None
            )
            if existing_cookie_key:
                existing = req_headers[existing_cookie_key].strip()
                req_headers[existing_cookie_key] = (
                    f"{existing}; {cookie_str}" if existing else cookie_str
                )
            else:
                req_headers["Cookie"] = cookie_str

        data: bytes | None = None
        if json is not None:
            data = json_module_dumps(json).encode("utf-8")
            if not any(k.lower() == "content-type" for k in req_headers):
                req_headers["Content-Type"] = "application/json"

        req = Request(url=url, method=method, data=data, headers=req_headers)
        try:
            with urlopen(
                req, timeout=self._timeout if timeout is None else timeout
            ) as resp:
                status = getattr(resp, "status", 200)
                content = resp.read()
        except HTTPError as e:
            # HTTPError carries a valid HTTP response body and status; preserve them.
            try:
                content = e.read()
            except Exception:
                content = b""
            response = HttpResponse(
                status_code=int(getattr(e, "code", 0) or 0), content=content
            )
            if response.status_code >= 400:
                raise HttpResponseError(response) from e
            return response
        except Exception as e:
            raise HttpRequestError(f"Request failed: {method} {url}", cause=e) from e

        response = HttpResponse(status_code=status, content=content)
        if response.status_code >= 400:
            raise HttpResponseError(response)
        return response

    def get(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        auth: tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return self._request(
            "GET",
            path,
            headers=headers,
            params=params,
            timeout=timeout,
            auth=auth,
            cookies=cookies,
            **kwargs,
        )

    def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        auth: tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return self._request(
            "POST",
            path,
            json=json,
            headers=headers,
            params=params,
            timeout=timeout,
            auth=auth,
            cookies=cookies,
            **kwargs,
        )

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
        # Mirror HttpClient._url behavior for parity and safety.
        parsed = urlsplit(path)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(
                    f"Unsupported URL scheme {parsed.scheme!r} for request path {path!r}; "
                    "only http:// and https:// are allowed"
                )
            return path
        if parsed.netloc:
            raise ValueError(
                f"Unsupported scheme-relative URL {path!r}; only http:// and https:// are allowed"
            )
        base = urlsplit(self._base_url)
        if base.scheme not in {"http", "https"}:
            raise ValueError(
                f"Unsupported base URL scheme {base.scheme!r} for base_url {self._base_url!r}; "
                "only http:// and https:// are allowed"
            )
        return urljoin(f"{self._base_url}/", path.lstrip("/"))

    async def get(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
        auth: aiohttp.BasicAuth | tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return await self._request(
            "GET",
            path,
            headers=headers,
            params=params,
            timeout=timeout,
            auth=auth,
            cookies=cookies,
            **kwargs,
        )

    async def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
        auth: aiohttp.BasicAuth | tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        return await self._request(
            "POST",
            path,
            json=json,
            headers=headers,
            params=params,
            timeout=timeout,
            auth=auth,
            cookies=cookies,
            **kwargs,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
        auth: aiohttp.BasicAuth | tuple[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise TypeError(
                f"Unsupported keyword arguments for AsyncHttpClient._request: {unexpected}. "
                "Supported: headers, params, timeout, auth, cookies."
            )
        auth_obj: aiohttp.BasicAuth | None
        if isinstance(auth, tuple):
            auth_obj = aiohttp.BasicAuth(*auth)
        else:
            auth_obj = auth
        url = self._url(path)
        try:
            async with self._client.request(
                method,
                url,
                json=json,
                headers=headers,
                params=params,
                timeout=timeout,
                auth=auth_obj,
                cookies=cookies,
            ) as resp:
                content = await resp.read()
                response = HttpResponse(status_code=resp.status, content=content)
        except asyncio.TimeoutError as e:
            raise HttpRequestError(f"Request failed: {method} {url}", cause=e) from e
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
