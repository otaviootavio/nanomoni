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


def deserialize_open_channel_request(envelope: Envelope) -> OpenChannelRequestPayload:
    """Decode and validate an open-channel request envelope payload."""
    payload_bytes = envelope_payload_bytes(envelope)
    payload_str = payload_bytes.decode("utf-8")
    return OpenChannelRequestPayload.model_validate_json(payload_str)


def deserialize_close_channel_request(
    envelope: Envelope,
) -> CloseChannelRequestPayload:
    """Decode and validate a close-channel request envelope payload."""
    payload_bytes = envelope_payload_bytes(envelope)
    payload_str = payload_bytes.decode("utf-8")
    return CloseChannelRequestPayload.model_validate_json(payload_str)


def deserialize_off_chain_tx(envelope: Envelope) -> OffChainTxPayload:
    """Decode and validate an off-chain tx envelope payload."""
    payload_bytes = envelope_payload_bytes(envelope)
    payload_str = payload_bytes.decode("utf-8")
    return OffChainTxPayload.model_validate_json(payload_str)


def verify_and_deserialize_off_chain_tx(
    public_key: ec.EllipticCurvePublicKey, envelope: Envelope
) -> OffChainTxPayload:
    """Verify an off-chain envelope and deserialize its payload in one step."""
    payload_bytes = verify_envelope_and_get_payload_bytes(public_key, envelope)
    payload_str = payload_bytes.decode("utf-8")
    return OffChainTxPayload.model_validate_json(payload_str)
