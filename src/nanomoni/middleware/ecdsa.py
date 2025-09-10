from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

import httpx
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


class ECDSASignatureMiddleware(BaseHTTPMiddleware):
    """Validate client certificate and ECDSA body signatures for mutating HTTP methods.

    Expected headers:
    - `X-Certificate`: Base64-encoded certificate bytes (JSON) issued by the issuer.
      The decoded JSON must include at least:
        { "client_public_key_der_b64": string, "balance": int }
    - `X-Certificate-Signature`: Base64-encoded DER ECDSA signature by the issuer over the raw certificate bytes.
    - `X-Signature`: Base64-encoded DER ECDSA signature over the raw request body by the client's private key.

    This MVP skips verification for safe/read-only paths and docs:
    - `/`, `/health`, `/docs`, `/redoc`, `/openapi.json`
    It also only verifies for methods that generally include a body:
    - POST, PUT, PATCH, DELETE
    """

    def __init__(
        self,
        app,
        issuer_base_url: Optional[str] = None,
        db_client=None,
        skip_paths: Optional[Iterable[str]] = None,
    ) -> None:
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
        self._issuer_base_url = issuer_base_url
        self._issuer_public_key = None  # in-memory cache of cryptography key
        self._issuer_public_key_der_b64 = None  # in-memory cache of DER b64
        self._db_client = db_client

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip paths like docs/health
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

        cert_b64 = request.headers.get("X-Certificate")
        cert_sig_b64 = request.headers.get("X-Certificate-Signature")
        body_sig_b64 = request.headers.get("X-Signature")

        if not cert_b64 or not cert_sig_b64 or not body_sig_b64:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Missing X-Certificate, X-Certificate-Signature, or X-Signature header",
                },
            )

        # Ensure issuer public key is available (in-memory -> redis -> fetch)
        try:
            issuer_public_key = await self._get_issuer_public_key_with_cache()
            if issuer_public_key is None:
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content={"detail": "Unable to obtain issuer public key"},
                )
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"detail": "Failed to obtain issuer public key"},
            )

        # Decode certificate + signature
        try:
            certificate_bytes = base64.b64decode(cert_b64, validate=True)
            certificate_signature_bytes = base64.b64decode(cert_sig_b64, validate=True)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "detail": "Invalid certificate or certificate signature encoding (expected base64)"
                },
            )

        # Verify issuer signature over certificate bytes
        try:
            issuer_public_key.verify(
                certificate_signature_bytes,
                certificate_bytes,
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid issuer signature on certificate"},
            )

        # Parse certificate to extract client public key
        try:
            cert_obj = json.loads(certificate_bytes.decode("utf-8"))
            client_pub_der_b64 = cert_obj["client_public_key_der_b64"]
            balance_value = cert_obj.get("balance")
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Malformed certificate payload"},
            )

        # Load client public key from certificate
        try:
            client_pub_der = base64.b64decode(client_pub_der_b64, validate=True)
            client_public_key = serialization.load_der_public_key(client_pub_der)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid client public key in certificate"},
            )

        # Verify client signature over request body
        try:
            body_signature_bytes = base64.b64decode(body_sig_b64, validate=True)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid body signature encoding (expected base64)"},
            )

        try:
            client_public_key.verify(
                body_signature_bytes, body, ec.ECDSA(hashes.SHA256())
            )
        except InvalidSignature:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid ECDSA signature for request body"},
            )

        # Attach certificate context for downstream handlers if needed
        request.state.client_public_key_der_b64 = client_pub_der_b64
        request.state.client_balance = balance_value
        request.state.certificate = cert_obj
        request.state.issuer_public_key_der_b64 = self._issuer_public_key_der_b64

        return await call_next(request)

    async def _get_issuer_public_key_with_cache(self):
        # # 1) In-memory cache
        # if self._issuer_public_key is not None:
        #     return self._issuer_public_key

        # # 2) Redis cache
        # der_b64 = await self._read_issuer_pubkey_from_cache()
        # if der_b64:
        #     try:
        #         der = base64.b64decode(der_b64, validate=True)
        #         self._issuer_public_key = serialization.load_der_public_key(der)
        #         self._issuer_public_key_der_b64 = der_b64
        #         return self._issuer_public_key
        #     except Exception:
        #         pass  # fall through to fetch

        # 3) Fetch from issuer
        fetched = await self._fetch_issuer_public_key()
        if not fetched:
            return None
        fetched_der_b64 = fetched
        try:
            der = base64.b64decode(fetched_der_b64, validate=True)
            self._issuer_public_key = serialization.load_der_public_key(der)
            self._issuer_public_key_der_b64 = fetched_der_b64
        except Exception:
            return None

        # Persist to Redis cache (best effort)
        try:
            await self._write_issuer_pubkey_to_cache(fetched_der_b64)
        except Exception:
            pass

        return self._issuer_public_key

    async def _read_issuer_pubkey_from_cache(self) -> Optional[str]:
        if not self._db_client:
            return None
        async with self._db_client.get_connection() as conn:
            return await conn.get("issuer_public_key:der_b64")

    async def _write_issuer_pubkey_to_cache(self, der_b64: str) -> None:
        if not self._db_client:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._db_client.get_connection() as conn:
            # Store both value and timestamp for potential inspection
            await conn.set("issuer_public_key:der_b64", der_b64)
            await conn.set("issuer_public_key:updated_at", now_iso)

    async def _fetch_issuer_public_key(self) -> Optional[str]:
        if not self._issuer_base_url:
            return None
        url = f"{self._issuer_base_url}/issuer/public-key"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            der_b64 = data.get("der_b64")
            return der_b64

    def _load_public_key(self, header_value: str):
        # Detect PEM vs base64 DER
        if "BEGIN PUBLIC KEY" in header_value:
            return serialization.load_pem_public_key(header_value.encode("utf-8"))

        try:
            der_bytes = base64.b64decode(header_value, validate=True)
        except Exception as exc:
            raise ValueError("Not PEM or base64 DER") from exc

        return serialization.load_der_public_key(der_bytes)
