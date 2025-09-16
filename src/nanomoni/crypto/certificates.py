from __future__ import annotations

import base64
import json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel


def canonicalize_json(data: dict) -> bytes:
    """Serialize dict to canonical JSON bytes for signing/verification."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_bytes(private_key, payload_bytes: bytes) -> str:
    """Sign bytes with ECDSA SHA256 and return base64-encoded DER signature."""
    signature_der = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature_der).decode("utf-8")


def verify_signature(public_key, payload_bytes: bytes, signature_b64: str) -> None:
    """Verify base64-encoded DER signature over payload bytes. Raises InvalidSignature on failure."""
    signature_bytes = base64.b64decode(signature_b64, validate=True)
    public_key.verify(signature_bytes, payload_bytes, ec.ECDSA(hashes.SHA256()))


def load_public_key_der_b64(der_b64: str):
    """Load a cryptography public key object from base64-encoded DER (SubjectPublicKeyInfo)."""
    der = base64.b64decode(der_b64, validate=True)
    return serialization.load_der_public_key(der)


def load_private_key_pem(pem_str: str):
    """Load a cryptography private key object from a PEM-formatted string."""
    return serialization.load_pem_private_key(pem_str.encode(), password=None)


def issue_certificate(private_key, payload: dict) -> str:
    """Issue a certificate to the client."""
    payload_bytes = canonicalize_json(payload)
    signature_b64 = sign_bytes(private_key, payload_bytes)
    return signature_b64


def verify_certificate(public_key, payload: dict, signature_b64: str) -> None:
    """Verify a certificate."""
    payload_bytes = canonicalize_json(payload)
    verify_signature(public_key, payload_bytes, signature_b64)


# Generic envelope helpers for arbitrary dict payloads


def issue_payload_envelope(private_key, payload: dict) -> tuple[str, str]:
    """Create a base64-encoded canonical JSON payload and its signature.

    Returns (certificate_b64, signature_b64).
    """
    payload_bytes = canonicalize_json(payload)
    signature_b64 = sign_bytes(private_key, payload_bytes)
    certificate_b64 = base64.b64encode(payload_bytes).decode("utf-8")
    return certificate_b64, signature_b64


def verify_payload_envelope(
    public_key, certificate_b64: str, signature_b64: str
) -> dict:
    """Verify an envelope and return the decoded dict payload."""
    payload_bytes = base64.b64decode(certificate_b64, validate=True)
    verify_signature(public_key, payload_bytes, signature_b64)
    return json.loads(payload_bytes.decode("utf-8"))


class PayChanCertificatePayload(BaseModel):
    """Payload for a payment channel certificate."""

    computed_id: str
    amount: int
    balance: int
    vendor_public_key_der_b64: str
    client_public_key_der_b64: str


def issuer_issue_paychan_certificate(
    private_key, payload: PayChanCertificatePayload
) -> str:
    """Issue a certificate to the client."""
    payload_bytes = canonicalize_json(payload.model_dump())
    signature_b64 = sign_bytes(private_key, payload_bytes)
    return signature_b64


def issuer_issue_paychan_certificate_envelope(
    private_key, payload: PayChanCertificatePayload
) -> tuple[str, str]:
    """Create the paychan certificate payload and signature.

    Returns a tuple of (certificate_b64, signature_b64).
    """
    payload_bytes = canonicalize_json(payload.model_dump())
    signature_b64 = sign_bytes(private_key, payload_bytes)
    certificate_b64 = base64.b64encode(payload_bytes).decode("utf-8")
    return certificate_b64, signature_b64


def issuer_verify_paychan_certificate(
    public_key, payload: PayChanCertificatePayload, signature_b64: str
) -> None:
    """Verify a certificate."""
    payload_bytes = canonicalize_json(payload.model_dump())
    verify_signature(public_key, payload_bytes, signature_b64)


def issuer_verify_paychan_certificate_envelope(
    public_key, certificate_b64: str, signature_b64: str
) -> PayChanCertificatePayload:
    """Verify a base64-encoded paychan certificate envelope and return the parsed payload model."""
    payload_bytes = base64.b64decode(certificate_b64, validate=True)
    verify_signature(public_key, payload_bytes, signature_b64)
    data = json.loads(payload_bytes.decode("utf-8"))
    return PayChanCertificatePayload(**data)


class RegistrationCertificatePayload(BaseModel):
    """Payload for initial issuer registration certificate."""

    client_public_key_der_b64: str
    balance: int


def issuer_issue_registration_certificate(
    private_key, payload: RegistrationCertificatePayload
) -> tuple[str, str]:
    """Create the registration certificate payload and signature.

    Returns a tuple of (certificate_b64, signature_b64).
    """
    payload_bytes = canonicalize_json(payload.model_dump())
    signature_b64 = sign_bytes(private_key, payload_bytes)
    certificate_b64 = base64.b64encode(payload_bytes).decode("utf-8")
    return certificate_b64, signature_b64


def issuer_verify_registration_certificate(
    public_key, certificate_b64: str, signature_b64: str
) -> RegistrationCertificatePayload:
    """Verify a registration certificate and return the parsed payload model on success."""
    payload_bytes = base64.b64decode(certificate_b64, validate=True)
    verify_signature(public_key, payload_bytes, signature_b64)
    data = json.loads(payload_bytes.decode("utf-8"))
    return RegistrationCertificatePayload(**data)
