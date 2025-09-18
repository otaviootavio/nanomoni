"""Data Transfer Objects for the issuer application layer."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, field_serializer


class StartRegistrationRequestDTO(BaseModel):
    """Client sends only its public key (DER b64) to start registration."""

    client_public_key_der_b64: str


class StartRegistrationResponseDTO(BaseModel):
    """Issuer returns a challenge id and a random nonce to be signed by the client."""

    challenge_id: UUID
    nonce_b64: str

    @field_serializer("challenge_id")
    def serialize_challenge_id(self, value: UUID) -> str:
        return str(value)


class CompleteRegistrationRequestDTO(BaseModel):
    """Client returns the challenge id and signature over the nonce."""

    challenge_id: UUID
    signature_der_b64: str


class RegistrationCertificateDTO(BaseModel):
    """Issuer-signed certificate with client public key and initial balance."""

    client_public_key_der_b64: str
    balance: int
    certificate_b64: str
    certificate_signature_b64: str
    # For now a simple self-describing envelope; could also add issuer signature if needed


class IssuerPublicKeyDTO(BaseModel):
    der_b64: str


# Payment channel DTOs
class OpenChannelRequestDTO(BaseModel):
    """Request to open a payment channel using a client-signed envelope."""

    client_public_key_der_b64: str
    open_payload_b64: str
    open_signature_b64: str


class OpenChannelResponseDTO(BaseModel):
    """Response containing the issuer-signed envelope describing the opened channel."""

    open_envelope_payload_b64: str
    open_envelope_signature_b64: str


class CloseChannelRequestDTO(BaseModel):
    """Vendor presents client-signed close envelope plus vendor's consent signature (detached) for closing."""

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    close_payload_b64: str
    client_close_signature_b64: str
    vendor_close_signature_b64: str


class CloseChannelResponseDTO(BaseModel):
    """Response after closing the channel with updated balances."""

    computed_id: str
    client_balance: int
    vendor_balance: int


class GetPaymentChannelRequestDTO(BaseModel):
    """Request to get a payment channel by its computed ID."""

    computed_id: str


class PaymentChannelResponseDTO(BaseModel):
    """Response with payment channel details."""

    channel_id: UUID
