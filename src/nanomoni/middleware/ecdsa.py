from __future__ import annotations

import base64
from typing import Callable, Iterable, Optional

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


class ECDSASignatureMiddleware(BaseHTTPMiddleware):
    """Validate ECDSA signatures for mutating HTTP methods.

    Expected headers:
    - `X-Public-Key`: The public key used to verify the signature.
        Supported formats:
          * PEM (full text with BEGIN/END lines)
          * Base64-encoded DER SubjectPublicKeyInfo
    - `X-Signature`: Base64-encoded DER ECDSA signature over the raw request body.

    This MVP skips verification for safe/read-only paths and docs:
    - `/`, `/health`, `/docs`, `/redoc`, `/openapi.json`
    It also only verifies for methods that generally include a body:
    - POST, PUT, PATCH, DELETE
    """

    def __init__(self, app, skip_paths: Optional[Iterable[str]] = None) -> None:
        super().__init__(app)
        self._skip_paths = set(
            skip_paths
            or [
                "/",
                "/health",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/api/v1/issuer/",
            ]
        )
        self._protected_methods = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip paths like docs/health and issuer flow (prefix match)
        path = request.url.path
        if (
            any(path.startswith(p) for p in self._skip_paths)
            or request.method.upper() not in self._protected_methods
        ):
            return await call_next(request)

        # Read and buffer the body so downstream can read it too
        body: bytes = await request.body()

        # Reconstruct request with a new receive that replays the body
        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

        public_key_header = request.headers.get("X-Public-Key")
        signature_header = request.headers.get("X-Signature")

        if not public_key_header or not signature_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing X-Public-Key or X-Signature header"},
            )

        try:
            public_key = self._load_public_key(public_key_header)
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid public key format. Send PEM or base64 DER"},
            )

        try:
            signature_bytes = base64.b64decode(signature_header, validate=True)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid signature encoding. Expected base64 DER"},
            )

        try:
            public_key.verify(signature_bytes, body, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid ECDSA signature"},
            )

        return await call_next(request)

    def _load_public_key(self, header_value: str):
        # Detect PEM vs base64 DER
        if "BEGIN PUBLIC KEY" in header_value:
            return serialization.load_pem_public_key(header_value.encode("utf-8"))

        try:
            der_bytes = base64.b64decode(header_value, validate=True)
        except Exception as exc:
            raise ValueError("Not PEM or base64 DER") from exc

        return serialization.load_der_public_key(der_bytes)
