from __future__ import annotations

import base64
import json
from typing import NewType
from functools import lru_cache

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel

# Stronger semantic aliases for base64-encoded fields
PayloadB64 = NewType("PayloadB64", str)
SignatureB64 = NewType("SignatureB64", str)
DERB64 = NewType("DERB64", str)


class Envelope(BaseModel):
    """Typed container for a base64-encoded canonical JSON payload and its signature."""

    payload_b64: PayloadB64
    signature_b64: SignatureB64


def json_to_bytes(data: dict) -> bytes:
    """Serialize dict to canonical JSON bytes for signing/verification."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_bytes(private_key: ec.EllipticCurvePrivateKey, payload_bytes: bytes) -> str:
    """Sign bytes with ECDSA SHA256 and return base64-encoded DER signature."""
    signature_der = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature_der).decode("utf-8")


def verify_signature_bytes(
    public_key: ec.EllipticCurvePublicKey, payload_bytes: bytes, signature_b64: str
) -> bool:
    """Verify base64-encoded DER signature over payload bytes. Raises InvalidSignature on failure."""
    signature_bytes = base64.b64decode(signature_b64, validate=True)
    public_key.verify(signature_bytes, payload_bytes, ec.ECDSA(hashes.SHA256()))
    return True


@lru_cache(maxsize=128)
def load_public_key_from_der_b64(der_b64: DERB64) -> ec.EllipticCurvePublicKey:
    """Load a cryptography public key object from base64-encoded DER (SubjectPublicKeyInfo)."""
    der = base64.b64decode(der_b64, validate=True)
    key = serialization.load_der_public_key(der)
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise TypeError("Expected an EllipticCurve public key")
    return key


@lru_cache(maxsize=128)
def load_private_key_from_pem(pem_str: str) -> ec.EllipticCurvePrivateKey:
    """Load a cryptography private key object from a PEM-formatted string."""
    key = serialization.load_pem_private_key(pem_str.encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TypeError("Expected an EllipticCurve private key")
    return key


def generate_envelope(
    private_key: ec.EllipticCurvePrivateKey, payload: dict
) -> Envelope:
    """Create a signed envelope over the given payload dict."""
    payload_bytes = json_to_bytes(payload)
    signature_b64 = sign_bytes(private_key, payload_bytes)
    return Envelope(
        payload_b64=PayloadB64(base64.b64encode(payload_bytes).decode("utf-8")),
        signature_b64=SignatureB64(signature_b64),
    )


def verify_envelope(public_key: ec.EllipticCurvePublicKey, envelope: Envelope) -> bool:
    """Verify a certificate over the decoded payload bytes contained in the envelope."""
    payload_bytes = base64.b64decode(envelope.payload_b64, validate=True)
    return verify_signature_bytes(public_key, payload_bytes, envelope.signature_b64)


def verify_envelope_and_get_payload_bytes(
    public_key: ec.EllipticCurvePublicKey, envelope: Envelope
) -> bytes:
    """Verify an envelope and return the decoded payload bytes.

    This avoids decoding the payload separately for verification and deserialization.
    """
    payload_bytes = base64.b64decode(envelope.payload_b64, validate=True)
    verify_signature_bytes(public_key, payload_bytes, envelope.signature_b64)
    return payload_bytes


def envelope_payload_bytes(envelope: Envelope) -> bytes:
    """Return the raw decoded payload bytes inside an envelope."""
    return base64.b64decode(envelope.payload_b64, validate=True)
