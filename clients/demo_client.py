from __future__ import annotations

import os
import json
import base64
from typing import Any, Dict

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}




def generate_ephemeral_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    # Use DER SubjectPublicKeyInfo then base64-encode for header safety
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(public_der).decode("utf-8")
    return private_key, public_b64


def sign_body(private_key, body: bytes) -> str:
    signature_der = private_key.sign(body, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature_der).decode("utf-8")


def to_canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    # Deterministic JSON encoding; we send these exact bytes as the request body
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def print_response(label: str, r: httpx.Response) -> None:
    try:
        data = r.json()
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        print(f"{label}: {r.status_code}\n{pretty}")
    except Exception:
        print(f"{label}: {r.status_code} {r.text}")


# New: issuer registration flow


def _fetch_issuer_public_key(client: httpx.Client, issuer_base: str):
    r = client.get(f"{issuer_base}/issuer/public-key")
    print_response("Issuer public key", r)
    r.raise_for_status()
    data = r.json()
    # Prefer DER b64 for compact transport
    der_b64 = data["der_b64"]
    der = base64.b64decode(der_b64)
    return serialization.load_der_public_key(der), der_b64


def _decode_and_validate_certificate(
    issuer_public_key, response_json: Dict[str, Any], our_public_key_b64: str
) -> Dict[str, Any]:
    # For MVP, server returns explicit certificate bytes (canonical JSON)
    certificate_bytes = base64.b64decode(response_json["certificate_b64"])  # bytes signed

    signature_b64 = response_json["certificate_signature_b64"]
    signature_bytes = base64.b64decode(signature_b64)

    # Verify signature
    issuer_public_key.verify(signature_bytes, certificate_bytes, ec.ECDSA(hashes.SHA256()))

    # Parse JSON certificate payload
    cert_obj = json.loads(certificate_bytes.decode("utf-8"))
    cert_pub_b64 = cert_obj["client_public_key_der_b64"]
    balance = int(cert_obj["balance"])

    # Validate certificate binds to our public key
    if cert_pub_b64 != our_public_key_b64:
        raise RuntimeError("Certificate public key does not match our key")

    return {
        "client_public_key_der_b64": cert_pub_b64,
        "balance": balance,
        "certificate_b64": base64.b64encode(certificate_bytes).decode("utf-8"),
        "certificate_signature_b64": signature_b64,
    }


def issuer_register(client: httpx.Client, issuer_base: str, public_key_b64: str, private_key) -> Dict[str, Any]:
    # 0) Fetch issuer public key (PEM/DER) for signature verification
    issuer_pub, issuer_pub_der_b64 = _fetch_issuer_public_key(client, issuer_base)

    # 1) Start registration
    start_payload = {"client_public_key_der_b64": public_key_b64}
    r = client.post(f"{issuer_base}/issuer/registration/start", json=start_payload)
    print_response("Issuer start registration", r)
    r.raise_for_status()
    start_data = r.json()
    challenge_id = start_data["challenge_id"]
    nonce_b64 = start_data["nonce_b64"]

    # 2) Sign nonce and complete registration
    signature_b64 = sign_body(private_key, base64.b64decode(nonce_b64))
    complete_payload = {"challenge_id": challenge_id, "signature_der_b64": signature_b64}
    r = client.post(f"{issuer_base}/issuer/registration/complete", json=complete_payload)
    print_response("Issuer complete registration", r)
    r.raise_for_status()
    resp_json = r.json()

    # 3) Decode and validate the returned certificate
    parsed_cert = _decode_and_validate_certificate(issuer_pub, resp_json, public_key_b64)
    print(f"Certificate verified. Balance: {parsed_cert['balance']}")

    return {
        **parsed_cert,
        "issuer_public_key_der_b64": issuer_pub_der_b64,
    }


def main() -> None:
    issuer_base_url = os.getenv("ISSUER_BASE_URL", "http://127.0.0.1:8001/api/v1")

    private_key, public_key_b64 = generate_ephemeral_keypair()

    with httpx.Client(timeout=10.0) as client:
        # Issuer registration flow (Alice registers with issuer Bob)
        cert = issuer_register(client, issuer_base_url, public_key_b64, private_key)
        print(json.dumps(cert, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main() 