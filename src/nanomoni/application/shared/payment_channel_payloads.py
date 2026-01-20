from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict

from ...crypto.certificates import (
    Envelope,
    envelope_payload_bytes,
    verify_envelope_and_get_payload_bytes,
)


class OpenChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed open-channel request envelope."""

    model_config = ConfigDict(extra="forbid")

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int


class SignatureSettlementPayload(BaseModel):
    """Signed close-channel statement.

    This is the payload that BOTH client and vendor sign during settlement/closure.
    Public keys are inferred from the stored PaymentChannel by channel_id.
    """

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    cumulative_owed_amount: int


class SignaturePaymentPayload(BaseModel):
    """Payload for a signature-mode off-chain payment from client to vendor.

    This is a client-signed monotonic statement of cumulative_owed_amount for a channel.
    We optimize space by omitting public keys; vendor/issuer infer them from channel_id.
    """

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    cumulative_owed_amount: int


def deserialize_open_channel_request(envelope: Envelope) -> OpenChannelRequestPayload:
    """Decode and validate an open-channel request envelope payload."""
    payload_bytes = envelope_payload_bytes(envelope)
    payload_str = payload_bytes.decode("utf-8")
    return OpenChannelRequestPayload.model_validate_json(payload_str)


def deserialize_signature_payment(envelope: Envelope) -> SignaturePaymentPayload:
    """Decode and validate a signature-mode payment envelope payload."""
    payload_bytes = envelope_payload_bytes(envelope)
    payload_str = payload_bytes.decode("utf-8")
    return SignaturePaymentPayload.model_validate_json(payload_str)


def verify_and_deserialize_signature_payment(
    public_key: ec.EllipticCurvePublicKey, envelope: Envelope
) -> SignaturePaymentPayload:
    """Verify a payment envelope and deserialize its signature-mode payload in one step."""
    payload_bytes = verify_envelope_and_get_payload_bytes(public_key, envelope)
    payload_str = payload_bytes.decode("utf-8")
    return SignaturePaymentPayload.model_validate_json(payload_str)
