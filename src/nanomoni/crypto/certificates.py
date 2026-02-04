from __future__ import annotations

import base64
import json
from typing import NewType
from functools import lru_cache

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel

# Stronger semantic aliases for base64-encoded fields
DERB64 = NewType("DERB64", str)


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


def dto_to_canonical_json_bytes(
    dto: BaseModel, exclude_fields: set[str] | None = None
) -> bytes:
    """Convert DTO to canonical JSON bytes for signature verification.

    Excludes signature fields (ending with '_signature_b64') and any fields
    specified in exclude_fields. None values are also excluded to match
    the original payload structure.

    Args:
        dto: Pydantic model instance to convert
        exclude_fields: Optional set of field names to exclude (in addition to signature fields)

    Returns:
        Canonical JSON bytes ready for signature verification
    """
    exclude = exclude_fields or set()
    # Get all fields, excluding None values and signature fields
    data = dto.model_dump(exclude_none=True)
    # Filter out signature fields and explicitly excluded fields
    # Signature fields are: exact match "signature_b64" or ending with "_signature_b64"
    filtered_data = {
        k: v
        for k, v in data.items()
        if k != "signature_b64"
        and not k.endswith("_signature_b64")
        and k not in exclude
    }
    return json_to_bytes(filtered_data)
