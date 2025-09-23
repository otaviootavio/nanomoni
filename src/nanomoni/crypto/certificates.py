from __future__ import annotations

import base64
import json
from typing import NewType

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel

# Stronger semantic aliases
PayloadB64 = NewType("PayloadB64", str)
SignatureB64 = NewType("SignatureB64", str)
DERB64 = NewType("DERB64", str)


class Envelope(BaseModel):
    """Typed container for a base64-encoded canonical JSON payload and its signature."""

    payload_b64: PayloadB64
    signature_b64: SignatureB64


class OpenChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed open-channel request envelope."""

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int


class OpenChannelResponsePayload(BaseModel):
    """Payload carried by the issuer-signed envelope returned after opening a channel."""

    computed_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    salt_b64: str
    amount: int
    balance: int


class CloseChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed close-channel request envelope."""

    computed_id: str
    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    owed_amount: int


class OffChainTxPayload(CloseChannelRequestPayload):
    """Payload for an off-chain transaction from client to vendor.

    This has the same structure as a close channel request because it represents
    a client-signed statement of the channel's final state.
    """

    pass


class CloseChannelResponsePayload(BaseModel):
    """Payload carried by the issuer-signed envelope after closing a channel."""

    computed_id: str
    client_balance: int
    vendor_balance: int


class RegistrationCertificatePayload(BaseModel):
    """Payload carried by the issuer-signed registration certificate."""

    client_public_key_der_b64: str
    balance: int


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


def load_public_key_from_der_b64(der_b64: DERB64) -> ec.EllipticCurvePublicKey:
    """Load a cryptography public key object from base64-encoded DER (SubjectPublicKeyInfo)."""
    der = base64.b64decode(der_b64, validate=True)
    return serialization.load_der_public_key(der)


def load_private_key_from_pem(pem_str: str) -> ec.EllipticCurvePrivateKey:
    """Load a cryptography private key object from a PEM-formatted string."""
    return serialization.load_pem_private_key(pem_str.encode(), password=None)


def generate_envelope(
    private_key: ec.EllipticCurvePrivateKey, payload: dict
) -> Envelope:
    """Issue a certificate to the client."""
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


def envelope_payload_bytes(envelope: Envelope) -> bytes:
    """Return the raw decoded payload bytes inside an envelope."""
    return base64.b64decode(envelope.payload_b64, validate=True)


def deserialize_open_channel_request(envelope: Envelope) -> OpenChannelRequestPayload:
    """Decode and validate an open-channel request envelope payload."""
    payload_bytes = base64.b64decode(envelope.payload_b64, validate=True)
    data = json.loads(payload_bytes.decode("utf-8"))
    return OpenChannelRequestPayload.model_validate(data)


def serialize_open_channel_response(
    private_key: ec.EllipticCurvePrivateKey,
    payload: OpenChannelResponsePayload,
) -> Envelope:
    """Serialize and sign the issuer's open-channel response payload into an envelope."""
    return generate_envelope(private_key, payload.model_dump())


def deserialize_close_channel_request(envelope: Envelope) -> CloseChannelRequestPayload:
    """Decode and validate a close-channel request envelope payload."""
    payload_bytes = base64.b64decode(envelope.payload_b64, validate=True)
    data = json.loads(payload_bytes.decode("utf-8"))
    return CloseChannelRequestPayload.model_validate(data)


def deserialize_off_chain_tx(envelope: Envelope) -> OffChainTxPayload:
    """Decode and validate an off-chain tx envelope payload."""
    payload_bytes = base64.b64decode(envelope.payload_b64, validate=True)
    data = json.loads(payload_bytes.decode("utf-8"))
    return OffChainTxPayload.model_validate(data)


def serialize_close_channel_response(
    private_key: ec.EllipticCurvePrivateKey,
    payload: CloseChannelResponsePayload,
) -> Envelope:
    """Serialize and sign the issuer's close-channel response payload into an envelope."""
    return generate_envelope(private_key, payload.model_dump())


def issuer_issue_registration_certificate(
    private_key: ec.EllipticCurvePrivateKey,
    payload: RegistrationCertificatePayload,
) -> tuple[str, str]:
    """Create an issuer-signed registration certificate and return (payload_b64, signature_b64)."""
    envelope = generate_envelope(private_key, payload.model_dump())
    return envelope.payload_b64, envelope.signature_b64
