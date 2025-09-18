from __future__ import annotations

import os
import json
import base64
from typing import Any, Dict, Optional

import httpx
from cryptography.hazmat.primitives import serialization

from nanomoni.envs.client_env import get_settings
from nanomoni.middleware.ecdsa import log_timing
from nanomoni.crypto.certificates import sign_bytes, load_public_key_der_b64


PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@log_timing("C_public_key_der_b64_from_private")
def public_key_der_b64_from_private(private_key) -> str:
    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(public_der).decode("utf-8")


@log_timing("C_sign_body")
def sign_body(private_key, body: bytes) -> str:
    return sign_bytes(private_key, body)


@log_timing("C_fetch_issuer_public_key")
def _fetch_issuer_public_key(client: httpx.Client, issuer_base: str):
    r = client.get(f"{issuer_base}/issuer/public-key")
    r.raise_for_status()
    data = r.json()
    # Prefer DER b64 for compact transport
    der_b64 = data["der_b64"]
    return load_public_key_der_b64(der_b64), der_b64


@log_timing("C_decode_certificate")
def _decode_certificate(response_json: Dict[str, Any]) -> Dict[str, Any]:
    certificate_bytes = base64.b64decode(
        response_json["certificate_b64"]
    )  # bytes signed
    signature_b64 = response_json["certificate_signature_b64"]
    signature_bytes = base64.b64decode(signature_b64)

    cert_obj = json.loads(certificate_bytes.decode("utf-8"))
    cert_pub_b64 = cert_obj["client_public_key_der_b64"]
    balance = int(cert_obj["balance"])

    return {
        "certificate_bytes": certificate_bytes,
        "certificate_signature_bytes": signature_bytes,
        "certificate_signature_b64": signature_b64,
        "client_public_key_der_b64": cert_pub_b64,
        "balance": balance,
    }


@log_timing("C_validate_certificate")
def _validate_certificate(
    issuer_public_key,
    certificate_bytes: bytes,
    signature_bytes: bytes,
    cert_pub_b64: str,
    our_public_key_b64: str,
) -> None:
    # Verify signature
    issuer_public_key.verify(signature_bytes, certificate_bytes)

    # Validate certificate binds to our public key
    if cert_pub_b64 != our_public_key_b64:
        raise RuntimeError("Certificate public key does not match our key")


@log_timing("C_issuer_register")
def issuer_register(
    client: httpx.Client, issuer_base: str, public_key_b64: str, private_key
) -> Dict[str, Any]:
    # 0) Fetch issuer public key (PEM/DER) for signature verification
    issuer_pub, issuer_pub_der_b64 = _fetch_issuer_public_key(client, issuer_base)

    # 1) Register with issuer
    reg_payload = {"client_public_key_der_b64": public_key_b64}
    r = client.post(f"{issuer_base}/issuer/register", json=reg_payload)
    r.raise_for_status()
    resp_json = r.json()

    # 2) Decode and validate the returned certificate
    decoded = _decode_certificate(resp_json)
    _validate_certificate(
        issuer_pub,
        decoded["certificate_bytes"],
        decoded["certificate_signature_bytes"],
        decoded["client_public_key_der_b64"],
        public_key_b64,
    )

    parsed_cert = {
        "client_public_key_der_b64": decoded["client_public_key_der_b64"],
        "balance": decoded["balance"],
        "certificate_b64": base64.b64encode(decoded["certificate_bytes"]).decode(
            "utf-8"
        ),
        "certificate_signature_b64": decoded["certificate_signature_b64"],
    }

    return {
        **parsed_cert,
        "issuer_public_key_der_b64": issuer_pub_der_b64,
    }


# ---------- Vendor helpers using signed headers ----------


@log_timing("C_auth_headers")
def _auth_headers(cert: Dict[str, Any], body: bytes, private_key) -> Dict[str, str]:
    return {
        "X-Certificate": cert["certificate_b64"],
        "X-Client-Public-Key": cert["client_public_key_der_b64"],
        "X-Signature": sign_body(private_key, body),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@log_timing("C_signed_request")
def _signed_request(
    client: httpx.Client,
    method: str,
    url: str,
    cert: Dict[str, Any],
    private_key,
    json_payload: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    if json_payload is None:
        body = b""
    else:
        body = json.dumps(
            json_payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    headers = _auth_headers(cert, body, private_key)
    return client.request(method, url, content=body, headers=headers)


# ---------- Vendor registration (challenge) ----------


@log_timing("C_vendor_register_start")
def vendor_register_start(
    client: httpx.Client, vendor_base: str, cert: Dict[str, Any]
) -> Dict[str, Any]:
    headers = {
        "X-Certificate": cert["certificate_b64"],
        "X-Certificate-Signature": cert["certificate_signature_b64"],
        "Accept": "application/json",
    }
    r = client.post(f"{vendor_base}/vendor/register", headers=headers)
    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_get_user_by_email")
def vendor_get_user_by_email(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
    email: str,
) -> Dict[str, Any]:
    r = _signed_request(
        client, "GET", f"{vendor_base}/users/email/{email}", cert, private_key
    )

    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_create_user")
def vendor_create_user(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
    name: str,
    email: str,
) -> Dict[str, Any]:
    payload = {"name": name, "email": email}
    r = _signed_request(
        client, "POST", f"{vendor_base}/users/", cert, private_key, payload
    )

    if r.status_code == 201:
        return r.json()
    if r.status_code == 409:
        # Fetch existing user by email
        return vendor_get_user_by_email(client, vendor_base, cert, private_key, email)
    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_create_task")
def vendor_create_task(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
    title: str,
    description: str,
    user_id: str,
) -> Dict[str, Any]:
    payload = {"title": title, "description": description, "user_id": user_id}
    r = _signed_request(
        client, "POST", f"{vendor_base}/tasks/", cert, private_key, payload
    )

    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_start_task")
def vendor_start_task(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
    task_id: str,
) -> Dict[str, Any]:
    r = _signed_request(
        client, "PATCH", f"{vendor_base}/tasks/{task_id}/start", cert, private_key
    )

    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_complete_task")
def vendor_complete_task(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
    task_id: str,
) -> Dict[str, Any]:
    r = _signed_request(
        client, "PATCH", f"{vendor_base}/tasks/{task_id}/complete", cert, private_key
    )

    r.raise_for_status()
    return r.json()


@log_timing("C_vendor_list_tasks")
def vendor_list_tasks(
    client: httpx.Client,
    vendor_base: str,
    cert: Dict[str, Any],
    private_key,
) -> None:
    r = _signed_request(client, "GET", f"{vendor_base}/tasks/", cert, private_key)

    r.raise_for_status()


@log_timing("C_main")
def main() -> None:
    issuer_base_url = os.getenv("ISSUER_BASE_URL")
    vendor_base_url = os.getenv("VENDOR_BASE_URL")

    settings = get_settings()
    private_key = serialization.load_pem_private_key(
        settings.client_private_key_pem.encode(),
        password=None,
    )
    public_key_b64 = public_key_der_b64_from_private(private_key)

    with httpx.Client(timeout=10.0) as client:
        # Issuer registration flow (Alice registers with issuer Bob)
        cert = issuer_register(client, issuer_base_url, public_key_b64, private_key)
        # print(json.dumps(cert, indent=2, ensure_ascii=False))

        # Vendor registration flow (trust establishment at vendor)
        start_data = vendor_register_start(client, vendor_base_url, cert)
        if start_data.get("status") != "trusted":
            raise RuntimeError(f"Unexpected registration start response: {start_data}")

        # Vendor flow using certificate and per-request signatures
        user = vendor_create_user(
            client,
            vendor_base_url,
            cert,
            private_key,
            name="Aliceeee",
            email="alicee@example2.com",
        )
        user_id = user["id"]


if __name__ == "__main__":
    main()
