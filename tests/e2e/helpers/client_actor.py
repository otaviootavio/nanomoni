"""ClientActor simulates client-side operations (key generation, signing)."""

from __future__ import annotations

import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
    OpenChannelRequestDTO,
)
from nanomoni.application.shared.payment_channel_payloads import (
    OpenChannelRequestPayload,
    OffChainTxPayload,
)
from nanomoni.crypto.certificates import Envelope, generate_envelope


class ClientActor:
    """Simulates client-side operations: key generation, signing, and envelope creation."""

    def __init__(self) -> None:
        """Initialize a new client actor with a generated key pair."""
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        public_key_der = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_der_b64 = base64.b64encode(public_key_der).decode("utf-8")

    def create_registration_request(self) -> RegistrationRequestDTO:
        """Create a registration request with this client's public key."""
        return RegistrationRequestDTO(client_public_key_der_b64=self.public_key_der_b64)

    def create_open_channel_request(
        self, vendor_public_key_der_b64: str, amount: int
    ) -> OpenChannelRequestDTO:
        """
        Create an open channel request signed by this client.

        Args:
            vendor_public_key_der_b64: Vendor's public key in DER base64 format
            amount: Amount to lock in the channel

        Returns:
            OpenChannelRequestDTO with signed envelope
        """
        payload = OpenChannelRequestPayload(
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            amount=amount,
        )
        envelope = generate_envelope(self.private_key, payload.model_dump())

        return OpenChannelRequestDTO(
            client_public_key_der_b64=self.public_key_der_b64,
            open_payload_b64=envelope.payload_b64,
            open_signature_b64=envelope.signature_b64,
        )

    def create_payment_envelope(
        self,
        computed_id: str,
        vendor_public_key_der_b64: str,
        owed_amount: int,
    ) -> Envelope:
        """
        Create a signed payment envelope for an off-chain transaction.

        Args:
            computed_id: Payment channel computed ID
            vendor_public_key_der_b64: Vendor's public key
            owed_amount: Amount owed to vendor

        Returns:
            Signed Envelope containing the payment payload
        """
        payload = OffChainTxPayload(
            computed_id=computed_id,
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            owed_amount=owed_amount,
        )
        return generate_envelope(self.private_key, payload.model_dump())
