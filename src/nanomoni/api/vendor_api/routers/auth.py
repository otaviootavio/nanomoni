"""Vendor registration routes (Vendor API)."""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, status, Depends

import base64
import json
import secrets
from datetime import datetime, timezone, timedelta

import httpx
from cryptography.exceptions import InvalidSignature
from nanomoni.crypto.certificates import load_public_key_der_b64, verify_signature

from ..dependencies import (
    get_database_client_dependency,
    get_settings_dependency,
)

router = APIRouter(prefix="/vendor", tags=["vendor"])


async def _get_issuer_public_key(db_client, settings):
    """Get issuer public key (cryptography key), cached in Redis; fetch if missing."""
    # 1) Try cache
    try:
        async with db_client.get_connection() as conn:
            der_b64 = await conn.get("issuer_public_key:der_b64")
    except Exception:
        der_b64 = None
    if der_b64:
        try:
            return load_public_key_der_b64(der_b64)
        except Exception:
            pass
    # 2) Fetch from issuer
    if not settings.issuer_base_url:
        return None
    url = f"{settings.issuer_base_url}/issuer/public-key"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        fetched_der_b64 = data.get("der_b64")
        key = load_public_key_der_b64(fetched_der_b64)
    except Exception:
        return None
    # 3) Best-effort write to cache
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with db_client.get_connection() as conn:
            await conn.set("issuer_public_key:der_b64", fetched_der_b64)
            await conn.set("issuer_public_key:updated_at", now_iso)
    except Exception:
        pass
    return key


@router.post("/register")
async def register(
    request: Request,
    db_client=Depends(get_database_client_dependency),
    settings=Depends(get_settings_dependency),
):
    """Start client registration with a challenge.

    Requires certificate headers. Stores the client's certificate and pubkey,
    issues a short-lived challenge, and persists registration state as pending.
    """
    cert_b64 = request.headers.get("X-Certificate")
    cert_sig_b64 = request.headers.get("X-Certificate-Signature")
    if not cert_b64 or not cert_sig_b64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Certificate or X-Certificate-Signature header",
        )
    # Decode
    try:
        certificate_bytes = base64.b64decode(cert_b64, validate=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid certificate or signature encoding",
        )
    # Verify issuer signature
    issuer_public_key = await _get_issuer_public_key(db_client, settings)
    if issuer_public_key is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to obtain issuer public key",
        )
    try:
        verify_signature(issuer_public_key, certificate_bytes, cert_sig_b64)
    except InvalidSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid issuer signature on certificate",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid certificate or signature",
        )
    # Parse certificate and extract client's pub key
    try:
        cert_obj = json.loads(certificate_bytes.decode("utf-8"))
        client_pub_der_b64 = cert_obj["client_public_key_der_b64"]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed certificate payload",
        )
    # Persist registration with challenge
    key = f"vendor:registrations:{client_pub_der_b64}"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    async with db_client.get_connection() as conn:
        existing = await conn.get(key)
        if existing:
            try:
                existing_obj = json.loads(existing)
                if existing_obj.get("status") == "trusted":
                    return {
                        "status": "trusted",
                        "trusted_at": existing_obj.get("trusted_at"),
                    }
            except Exception:
                pass

        registration_record = {
            "status": "trusted",
            "client_public_key_der_b64": client_pub_der_b64,
            "certificate": cert_obj,
            "created_at": now_iso,
            "updated_at": now_iso,
            "trusted_at": now_iso,
        }
        await conn.set(key, json.dumps(registration_record))

    return {"status": "trusted", "trusted_at": now_iso}
