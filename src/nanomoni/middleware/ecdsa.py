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
import time
import functools
import inspect

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


def log_timing(tag: Optional[str] = None):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                t0 = time.time()
                try:
                    return await func(*args, **kwargs)
                finally:
                    dt_ms = (time.time() - t0) * 1000.0
                    print(f"[ECDSA-TIME][{tag or func.__name__}] {dt_ms:.3f}ms")

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                t0 = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    dt_ms = (time.time() - t0) * 1000.0
                    print(f"[ECDSA-TIME][{datetime.now().isoformat()}] [{tag or func.__name__}] {dt_ms:.3f}ms")

            return sync_wrapper

    return decorator


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
    It verifies for these methods:
    - GET, POST, PUT, PATCH, DELETE
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
        self._protected_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        self._issuer_base_url = issuer_base_url
        self._issuer_public_key = None  # in-memory cache of cryptography key
        self._issuer_public_key_der_b64 = None  # in-memory cache of DER b64
        self._db_client = db_client

    @log_timing("D0_dispatch")
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip if path/method not protected
        if self._should_skip(request):
            return await call_next(request)

        # Buffer body so downstream can read it too
        request, body = await self._buffer_request_body(request)

        # Required headers
        cert_b64, cert_sig_b64, body_sig_b64, error_response = self._extract_required_headers(request)
        if error_response:
            return error_response

        # Ensure issuer public key is available
        try:
            issuer_public_key = await self._get_issuer_public_key_with_cache()
            if issuer_public_key is None:
                return self._bad_gateway("Unable to obtain issuer public key")
        except Exception:
            return self._bad_gateway("Failed to obtain issuer public key")

        # Decode certificate + signature
        certificate_bytes, certificate_signature_bytes, error_response = self._decode_certificate_and_signature(cert_b64, cert_sig_b64)
        if error_response:
            return error_response

        # Verify issuer signature over certificate bytes
        if not self._verify_issuer_signature(issuer_public_key, certificate_signature_bytes, certificate_bytes):
            return self._unauthorized("Invalid issuer signature on certificate")

        # Parse certificate to extract client public key
        cert_obj, client_pub_der_b64, balance_value, error_response = self._parse_certificate_payload(certificate_bytes)
        if error_response:
            return error_response

        # Load client public key from certificate
        client_public_key, error_response = self._load_client_public_key_from_der_b64(client_pub_der_b64)
        if error_response:
            return error_response

        # Decode body signature
        body_signature_bytes, error_response = self._decode_body_signature(body_sig_b64)
        if error_response:
            return error_response

        # Verify client signature over request body
        if not self._verify_client_body_signature(client_public_key, body_signature_bytes, body):
            return self._unauthorized("Invalid ECDSA signature for request body")

        # Attach certificate context for downstream handlers if needed
        self._attach_request_context(
            request=request,
            client_pub_der_b64=client_pub_der_b64,
            balance_value=balance_value,
            cert_obj=cert_obj,
        )
 
        return await call_next(request)

    @log_timing("H1_should_skip")
    def _should_skip(self, request: Request) -> bool:
        path = request.url.path
        return (
            path in self._skip_paths
            or request.method.upper() not in self._protected_methods
        )

    @log_timing("H2_buffer_request_body")
    async def _buffer_request_body(self, request: Request) -> tuple[Request, bytes]:
        body: bytes = await request.body()

        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        return Request(request.scope, receive), body

    @log_timing("H3_extract_required_headers")
    def _extract_required_headers(self, request: Request):
        cert_b64 = request.headers.get("X-Certificate")
        cert_sig_b64 = request.headers.get("X-Certificate-Signature")
        body_sig_b64 = request.headers.get("X-Signature")
        if not cert_b64 or not cert_sig_b64 or not body_sig_b64:
            return None, None, None, self._unauthorized(
                "Missing X-Certificate, X-Certificate-Signature, or X-Signature header"
            )
        return cert_b64, cert_sig_b64, body_sig_b64, None

    def _json_error(self, status_code: int, detail: str) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": detail})

    def _bad_request(self, detail: str) -> JSONResponse:
        return self._json_error(status.HTTP_400_BAD_REQUEST, detail)

    def _unauthorized(self, detail: str) -> JSONResponse:
        return self._json_error(status.HTTP_401_UNAUTHORIZED, detail)

    def _bad_gateway(self, detail: str) -> JSONResponse:
        return self._json_error(status.HTTP_502_BAD_GATEWAY, detail)

    @log_timing("H5_decode_certificate_and_signature")
    def _decode_certificate_and_signature(self, cert_b64: str, cert_sig_b64: str):
        try:
            certificate_bytes = base64.b64decode(cert_b64, validate=True)
            certificate_signature_bytes = base64.b64decode(cert_sig_b64, validate=True)
            return certificate_bytes, certificate_signature_bytes, None
        except Exception:
            return None, None, self._bad_request(
                "Invalid certificate or certificate signature encoding (expected base64)"
            )

    @log_timing("H6_verify_issuer_signature")
    def _verify_issuer_signature(self, issuer_public_key, certificate_signature_bytes: bytes, certificate_bytes: bytes) -> bool:
        try:
            issuer_public_key.verify(
                certificate_signature_bytes,
                certificate_bytes,
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except InvalidSignature:
            return False

    @log_timing("H7_parse_certificate_payload")
    def _parse_certificate_payload(self, certificate_bytes: bytes):
        try:
            cert_obj = json.loads(certificate_bytes.decode("utf-8"))
            client_pub_der_b64 = cert_obj["client_public_key_der_b64"]
            balance_value = cert_obj.get("balance")
            return cert_obj, client_pub_der_b64, balance_value, None
        except Exception:
            return None, None, None, self._bad_request("Malformed certificate payload")

    @log_timing("H8_load_client_public_key")
    def _load_client_public_key_from_der_b64(self, client_pub_der_b64: str):
        try:
            client_pub_der = base64.b64decode(client_pub_der_b64, validate=True)
            client_public_key = serialization.load_der_public_key(client_pub_der)
            return client_public_key, None
        except Exception:
            return None, self._bad_request("Invalid client public key in certificate")

    @log_timing("H9_decode_body_signature")
    def _decode_body_signature(self, body_sig_b64: str):
        try:
            body_signature_bytes = base64.b64decode(body_sig_b64, validate=True)
            return body_signature_bytes, None
        except Exception:
            return None, self._bad_request(
                "Invalid body signature encoding (expected base64)"
            )

    @log_timing("H10_verify_client_body_signature")
    def _verify_client_body_signature(self, client_public_key, body_signature_bytes: bytes, body: bytes) -> bool:
        try:
            client_public_key.verify(
                body_signature_bytes, body, ec.ECDSA(hashes.SHA256())
            )
            return True
        except InvalidSignature:
            return False

    @log_timing("H11_attach_request_context")
    def _attach_request_context(
        self,
        request: Request,
        client_pub_der_b64: str,
        balance_value,
        cert_obj: dict,
    ) -> None:
        request.state.client_public_key_der_b64 = client_pub_der_b64
        request.state.client_balance = balance_value
        request.state.certificate = cert_obj
        request.state.issuer_public_key_der_b64 = self._issuer_public_key_der_b64

    @log_timing("H12_get_issuer_public_key_with_cache")
    async def _get_issuer_public_key_with_cache(self):
        

        # 1) Redis cache
        der_b64 = await self._read_issuer_pubkey_from_cache()
        if der_b64:
            try:
                der = base64.b64decode(der_b64, validate=True)
                self._issuer_public_key = serialization.load_der_public_key(der)
                self._issuer_public_key_der_b64 = der_b64
                return self._issuer_public_key
            except Exception:
                pass  # fall through to fetch

        # 2) Fetch from issuer
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

    @log_timing("H13_read_cache")
    async def _read_issuer_pubkey_from_cache(self) -> Optional[str]:
        if not self._db_client:
            return None
        async with self._db_client.get_connection() as conn:
            return await conn.get("issuer_public_key:der_b64")

    @log_timing("H14_write_cache")
    async def _write_issuer_pubkey_to_cache(self, der_b64: str) -> None:
        if not self._db_client:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._db_client.get_connection() as conn:
            # Store both value and timestamp for potential inspection
            await conn.set("issuer_public_key:der_b64", der_b64)
            await conn.set("issuer_public_key:updated_at", now_iso)

    @log_timing("H15_fetch_issuer_public_key")
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

    @log_timing("H16_load_public_key")
    def _load_public_key(self, header_value: str):
        # Detect PEM vs base64 DER
        if "BEGIN PUBLIC KEY" in header_value:
            return serialization.load_pem_public_key(header_value.encode("utf-8"))

        try:
            der_bytes = base64.b64decode(header_value, validate=True)
        except Exception as exc:
            raise ValueError("Not PEM or base64 DER") from exc

        return serialization.load_der_public_key(der_bytes)
